"""Bonvoice PBX — click-to-call from the lead worklists, plus call-log ingest.

Click2Call bridges two legs: Bonvoice rings the RM's own phone first, and when they
answer it dials the lead and joins them. The laptop only triggers it — no audio ever
touches the browser, which is why users.phone is mandatory rather than nice to have.

Bonvoice echoes `callBackParams` verbatim on every call-log callback, so we send the
lead id when placing the call and get it back. Logs attach by explicit id instead of
by matching phone numbers.

The callback fires three lifecycle events (0 initiated, 1 answered, 2 hangup) per leg,
up to six per conversation — so the handler acks immediately and persists in a
background task, the same shape as the Gupshup webhook.
"""
import asyncio
import json
import logging
import re
import secrets
from datetime import datetime
from urllib.parse import parse_qsl
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import desc, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..core.auth import current_user, require_admin
from ..db import neon_engine
from ..models import CallLog

log = logging.getLogger("bonvoice")
router = APIRouter(tags=["bonvoice"])

AUTOCALL_BRIDGE = "3"  # autocallType for a two-leg bridged call (4 = TTS, 5 = voicebot)
CALL_ANSWERED = "1"    # callType on the lifecycle callback
CALL_HANGUP = "2"

# Token cache. The docs give no TTL, so it's held until a 401 forces a refresh rather
# than expiring on a guess. Process-local: re-authing per instance is one cheap call.
_token: dict = {"value": ""}


def _digits(phone: str | None) -> str:
    """Bonvoice takes Indian numbers as 9846098460 / 09846098460 / 919846098460 /
    +919846098460 — the last 10 digits satisfy all of those forms."""
    d = re.sub(r"\D", "", phone or "")
    return d[-10:] if len(d) >= 10 else ""


def _mask(phone: str) -> str:
    return ("•" * max(0, len(phone) - 4)) + phone[-4:] if phone else "—"


def _rejection_reason(r: httpx.Response) -> str | None:
    """Why Bonvoice refused, or None if it accepted.

    Their API answers 200 for both outcomes, so the body is the only signal. A
    rejection carries {"error": "..."}; an acceptance carries responseType "Success".
    Anything unparseable is treated as accepted — the call may well have been placed,
    and claiming failure would be worse than staying quiet.
    """
    try:
        body = r.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    if body.get("error"):
        return str(body["error"])
    rtype = str(body.get("responseType", "")).lower()
    if rtype and rtype != "success":
        return str(body.get("responseDescription") or body.get("responseType"))
    return None


async def _auth_token(force: bool = False) -> str:
    """Exchange username/password for a token, cached. A pre-issued BONVOICE_TOKEN
    short-circuits this entirely."""
    s = get_settings()
    if s.BONVOICE_TOKEN:
        return s.BONVOICE_TOKEN
    if _token["value"] and not force:
        return _token["value"]
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(
            f"{s.bonvoice_base}/usermanagement/external-auth/",
            json={"username": s.BONVOICE_USERNAME, "password": s.BONVOICE_PASSWORD},
        )
    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Bonvoice auth failed: {r.text[:200]}")
    tok = ((r.json() or {}).get("data") or {}).get("token")
    if not tok:
        raise HTTPException(status_code=502, detail="Bonvoice auth returned no token")
    _token["value"] = tok
    return tok


# --- outbound: click-to-call --------------------------------------------------

def new_event_id() -> str:
    """docs: unique alphanumeric, 8–16 chars."""
    return uuid4().hex[:16]


async def place_bridge(rm_phone: str, lead_phone: str, callback_params: dict,
                       event_id: str | None = None) -> str:
    """Place one Click2Call bridge and return its eventID.

    Leg A is the RM's handset, leg B the lead; Bonvoice only dials the lead once the
    RM picks up. `callback_params` is echoed verbatim on every lifecycle callback, so
    whatever we need to reconcile the call later goes in there.

    Pass `event_id` to reserve it beforehand — callbacks can land before this function
    returns, and a caller that stores the id afterwards would miss them.

    Raises HTTPException on anything that isn't an accepted call — including the
    HTTP-200-with-an-error-body case, which is how Bonvoice reports most rejections.
    """
    s = get_settings()
    event_id = event_id or new_event_id()
    payload = {
        "autocallType": AUTOCALL_BRIDGE,
        "destination": rm_phone,          # leg A — rings the RM
        "ringStrategy": "ringall",
        "legACallerID": s.BONVOICE_DID,
        "legAChannelID": s.BONVOICE_CHANNEL_ID,
        "legADialAttempts": "1",
        "legBDestination": lead_phone,    # leg B — the lead
        "legBCallerID": s.BONVOICE_DID,
        "legBChannelID": s.BONVOICE_CHANNEL_ID,
        "legBDialAttempts": "1",
        "eventID": event_id,
        # echoed back on every call-log callback — this is what links logs to leads
        "callBackParams": callback_params,
    }

    async def _post(tok: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=25.0) as client:
            return await client.post(
                f"{s.bonvoice_base}/autoDialManagement/autoCallBridging/",
                json=payload, headers={"Authorization": f"Token {tok}"},
            )

    try:
        r = await _post(await _auth_token())
        if r.status_code == 401:  # cached token went stale — re-auth once, then give up
            r = await _post(await _auth_token(force=True))
    except httpx.HTTPError as e:
        log.warning("bonvoice call failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Couldn't reach Bonvoice: {e}")

    if r.status_code >= 300:
        log.warning("bonvoice rejected the call (%s): %s", r.status_code, r.text[:300])
        raise HTTPException(status_code=502, detail=f"Bonvoice rejected the call: {r.text[:200]}")

    # A rejection comes back as HTTP 200 with an error body — e.g.
    # {"error": "DID is not configured"} — so the status code alone means nothing.
    # Success looks like {"responseCode": 200, "responseType": "Success", ...}.
    problem = _rejection_reason(r)
    if problem:
        log.warning("bonvoice rejected the call: %s", problem)
        raise HTTPException(status_code=502, detail=f"Bonvoice rejected the call: {problem}")
    return event_id


class CallRequest(BaseModel):
    lead_id: UUID


@router.post("/bonvoice/call")
async def bonvoice_call(req: CallRequest, user: dict = Depends(current_user)):
    """Ring this user's phone, then bridge to the lead. The lead sees the DID; neither
    side ever sees the other's real number."""
    s = get_settings()
    if not s.bonvoice_configured:
        raise HTTPException(
            status_code=503,
            detail="Calling isn't set up yet — BONVOICE_DID plus either BONVOICE_TOKEN "
                   "or BONVOICE_USERNAME + BONVOICE_PASSWORD are missing.",
        )
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")

    async with engine.connect() as conn:
        lead = (await conn.execute(
            text("SELECT phone FROM leads WHERE id = :id"), {"id": req.lead_id}
        )).mappings().first()
        rm = (await conn.execute(
            text("SELECT phone FROM users WHERE lower(email) = lower(:e)"),
            {"e": user.get("email")},
        )).mappings().first()

    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    lead_phone = _digits(lead["phone"])
    if not lead_phone:
        raise HTTPException(status_code=400, detail="This lead has no usable phone number.")
    rm_phone = _digits(rm["phone"] if rm else None)
    if not rm_phone:
        # the bridge rings the caller's own handset first — without a number on file
        # there is nothing to ring, and no useful call can be placed
        raise HTTPException(
            status_code=400,
            detail="Add your mobile number in Settings — the call rings your phone first.",
        )

    event_id = await place_bridge(
        rm_phone, lead_phone,
        {"lead_id": str(req.lead_id), "actor": user.get("email")},
    )
    log.info("bonvoice call placed by=%s rm=%s lead=%s event=%s",
             user.get("email"), _mask(rm_phone), _mask(lead_phone), event_id)
    return {"status": "ringing", "event_id": event_id, "rm_phone_masked": _mask(rm_phone)}


# --- pull: ask Bonvoice how a call went ---------------------------------------
#
# The callback is push; this is the same information pulled. It exists because a
# callback that never arrives (URL not registered, 403, network drop) otherwise leaves
# a call ringing forever as far as we're concerned.

def _field(record: dict, *names: str):
    """Case-insensitive field read. The docs give `callType` and `Status` for the
    callback, but the log endpoint's exact casing isn't documented — so match loosely
    rather than silently reading None off a capitalisation difference."""
    lowered = {str(k).lower(): v for k, v in record.items()}
    for n in names:
        v = lowered.get(n.lower())
        if v not in (None, ""):
            return v
    return None


def log_records(body) -> list[dict]:
    """Pull the call records out of whatever envelope the response uses — a bare list,
    or a dict wrapping one, or a single record."""
    if isinstance(body, list):
        return [r for r in body if isinstance(r, dict)]
    if not isinstance(body, dict):
        return []
    for key in ("data", "result", "results", "records", "logs", "calls"):
        inner = body.get(key)
        if isinstance(inner, list):
            return [r for r in inner if isinstance(r, dict)]
        if isinstance(inner, dict):
            return log_records(inner)
    # a dict of scalars is the record itself
    return [body] if any(_field(body, k) for k in ("callID", "Status", "EndTime", "callType")) else []


def read_call_state(records: list[dict]) -> tuple[bool, bool, str | None]:
    """(ended, answered, status) as read from a set of log records.

    Ended is inferred from an end time or a hangup lifecycle marker; a record set with
    neither means the call is still up, so we say nothing and poll again.
    """
    ended = answered = False
    status = None
    for r in records:
        ctype = str(_field(r, "callType", "CallType") or "")
        st = _field(r, "Status", "AgentStatus")
        if _field(r, "EndTime", "end_time") or ctype == CALL_HANGUP:
            ended = True
        if ctype == CALL_ANSWERED or str(st or "").upper().startswith("ANSWER"):
            answered = True
        if st:
            status = str(st)
    return ended, answered, status


async def fetch_call_state(event_id: str) -> tuple[bool, bool, str | None] | None:
    """Ask Bonvoice how the call for `event_id` is doing. None = couldn't tell."""
    s = get_settings()

    async def _get(tok: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=20.0) as client:
            return await client.get(f"{s.bonvoice_base}/get-autocall-log/{event_id}/",
                                    headers={"Authorization": f"Token {tok}"})

    try:
        r = await _get(await _auth_token())
        if r.status_code == 401:
            r = await _get(await _auth_token(force=True))
    except (httpx.HTTPError, HTTPException) as e:
        log.warning("bonvoice: call-log fetch failed for %s: %s", event_id, e)
        return None
    if r.status_code >= 300:
        log.warning("bonvoice: call-log %s returned %s: %s", event_id, r.status_code, r.text[:200])
        return None
    try:
        records = log_records(r.json())
    except ValueError:
        log.warning("bonvoice: call-log %s wasn't JSON: %s", event_id, r.text[:200])
        return None
    if not records:
        # Logged in full once per call: if the envelope differs from what log_records
        # expects, this is the only way to see it without a live account.
        log.info("bonvoice: no call records parsed for %s — raw: %s", event_id, r.text[:600])
        return None
    return read_call_state(records)


# --- inbound: call logs -------------------------------------------------------

def _check_token(request: Request) -> None:
    secret = get_settings().BONVOICE_WEBHOOK_SECRET.strip()
    if secret and not secrets.compare_digest(request.query_params.get("token", ""), secret):
        raise HTTPException(status_code=403, detail="invalid token")


def parse_body(raw: bytes, content_type: str) -> dict:
    """Bonvoice sends the same fields as JSON or x-www-form-urlencoded — which one is
    an account setting, so accept both regardless of the declared content type."""
    body = raw.decode("utf-8", "replace")
    if not body:
        return {}
    if "form-urlencoded" not in content_type:
        try:
            parsed = json.loads(body)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass  # mislabelled content type — fall through to form parsing
    return dict(parse_qsl(body))


def _dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def lead_id_from(params) -> UUID | None:
    """callBackParams arrives as an object on JSON callbacks and a JSON string on
    form-encoded ones."""
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except json.JSONDecodeError:
            return None
    if not isinstance(params, dict):
        return None
    try:
        return UUID(str(params.get("lead_id")))
    except (ValueError, TypeError, AttributeError):
        return None


async def _release_dial_slot(engine, body: dict) -> None:
    """Hangup frees the auto-dialer slot — that's what lets the next lead ring on this
    RM's phone.

    Deliberately separate from the call-log upsert, and run first: a callback with no
    callID, or one whose log row fails to write, must still end the call as far as the
    dialer is concerned. Leaving a slot stuck reads as "Ringing…" forever and silently
    costs that RM the rest of the campaign.

    Both legs report a hangup; the WHERE on status='dialing' makes the second a no-op.
    """
    call_type = str(body.get("callType", ""))
    event_id = body.get("eventID")
    if not event_id or call_type not in (CALL_ANSWERED, CALL_HANGUP):
        return
    status = body.get("Status") or body.get("AgentStatus") or None
    # 'answered' is OR-ed and never cleared: the answer event arrives before the
    # hangup, and it's what decides whether this lead is owed a retry
    answered = call_type == CALL_ANSWERED or str(status or "").upper().startswith("ANSWER")
    ends = call_type == CALL_HANGUP
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("""UPDATE dial_queue
                           SET status   = CASE WHEN :ends THEN 'done' ELSE status END,
                               ended_at = CASE WHEN :ends THEN now() ELSE ended_at END,
                               outcome  = COALESCE(:outcome, outcome),
                               answered = answered OR :answered
                         WHERE event_id = :eid AND status = 'dialing'"""),
                {"eid": str(event_id), "outcome": status, "answered": answered, "ends": ends},
            )
    except Exception:  # noqa: BLE001 — the callback was already acked
        log.exception("bonvoice: failed to release dial slot for event %s", event_id)


async def _persist(body: dict) -> None:
    """Upsert the leg with only what this lifecycle event knows.

    Every field uses COALESCE precedence so a late 'initiated' can't blank the
    hangup's EndTime, and `answered` is OR-ed so it never flips back to false.
    """
    engine = neon_engine()
    if engine is None:
        return
    await _release_dial_slot(engine, body)

    call_id, leg = body.get("callID"), (body.get("Leg") or "A")
    if not call_id:
        log.warning("bonvoice: callback with no callID — logged nothing (type=%s event=%s)",
                    body.get("callType"), body.get("eventID"))
        return
    values = {
        "call_id": str(call_id), "leg": str(leg),
        "event_id": body.get("eventID") or None,
        "lead_id": lead_id_from(body.get("callBackParams")),
        "direction": body.get("Direction") or None,
        "source_number": body.get("SourceNumber") or None,
        "destination_number": body.get("DestinationNumber") or None,
        "display_number": body.get("DisplayNumber") or None,
        "status": body.get("Status") or None,
        "agent_status": body.get("AgentStatus") or None,
        "answered": str(body.get("callType", "")) == CALL_ANSWERED,
        "start_at": _dt(body.get("StartTime")),
        "end_at": _dt(body.get("EndTime")),
        # the recording — Bonvoice's docs write it ResourceURL, their support call it
        # resourceurl, so read it case-insensitively rather than lose recordings to a
        # capital letter
        "recording_url": _field(body, "ResourceURL", "recordingURL") or None,
        "raw": body,
    }
    stmt = pg_insert(CallLog).values(**values)
    updates = {k: text(f"COALESCE(EXCLUDED.{k}, call_logs.{k})")
               for k in values if k not in ("call_id", "leg", "answered")}
    updates["answered"] = text("call_logs.answered OR EXCLUDED.answered")
    try:
        async with engine.begin() as conn:
            await conn.execute(stmt.on_conflict_do_update(
                index_elements=[CallLog.call_id, CallLog.leg], set_=updates))
    except Exception:  # noqa: BLE001 — the callback was already acked
        log.exception("bonvoice: failed to persist call log")


@router.get("/bonvoice/webhook")
async def bonvoice_verify(request: Request):
    """Smoke test — confirms the URL and token before handing it to Bonvoice."""
    _check_token(request)
    return {"status": "ok"}


@router.post("/bonvoice/webhook", status_code=200, response_class=Response)
async def bonvoice_webhook(request: Request):
    """Up to six callbacks per conversation — ack instantly, persist in background."""
    _check_token(request)
    try:
        body = parse_body(await request.body(), request.headers.get("content-type", ""))
    except Exception:  # noqa: BLE001
        log.exception("bonvoice: unreadable callback body")
        return Response(status_code=200)
    log.info("bonvoice callback type=%s leg=%s call=%s status=%s",
             body.get("callType"), body.get("Leg"), body.get("callID"), body.get("Status"))
    asyncio.create_task(_persist(body))
    return Response(status_code=200)


CALL_LOG_FROM = "FROM call_logs c LEFT JOIN leads l ON l.id = c.lead_id"


def call_log_filters(q: str | None, answered: bool | None) -> tuple[str, dict]:
    """WHERE clause + bind params for the call-log list. Split out so the same clause
    drives both the page and its count, and so it's testable without a database."""
    where, params = [], {}
    if q:
        where.append("(c.source_number ILIKE :q OR c.destination_number ILIKE :q "
                     "OR c.display_number ILIKE :q OR l.name ILIKE :q)")
        params["q"] = f"%{q}%"
    if answered is not None:
        where.append("c.answered = :answered")
        params["answered"] = answered
    return (" WHERE " + " AND ".join(where)) if where else "", params


@router.get("/bonvoice/calls", dependencies=[Depends(require_admin)])
async def call_log(
    q: str | None = Query(None),          # matches any phone number or the lead's name
    answered: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Every call leg Bonvoice has reported, newest first — backs the Call Log page.

    One conversation is two legs (A = the RM's handset, B = the lead), so a bridged
    call shows as two rows. The recording arrives as ResourceURL on the hangup callback.
    """
    engine = neon_engine()
    if engine is None:
        return {"items": [], "total": 0}
    clause, params = call_log_filters(q, answered)
    async with engine.connect() as conn:
        total = (await conn.execute(
            text(f"SELECT count(*) {CALL_LOG_FROM}{clause}"), params)).scalar()
        rows = (await conn.execute(text(f"""
            SELECT c.call_id, c.leg, c.event_id, c.lead_id, l.name AS lead_name,
                   c.direction, c.source_number, c.destination_number, c.display_number,
                   c.status, c.agent_status, c.answered, c.start_at, c.end_at,
                   c.recording_url,
                   -- placed_by is only filled for calls the dialer placed; for a
                   -- click-to-call the actor rides along in the echoed callBackParams
                   COALESCE(c.placed_by, c.raw->'callBackParams'->>'actor') AS placed_by
            {CALL_LOG_FROM}{clause}
             ORDER BY COALESCE(c.start_at, c.created_at) DESC
             LIMIT :limit OFFSET :offset"""),
            {**params, "limit": limit, "offset": offset})).mappings().all()
    return {"items": [
        {k: (v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, UUID) else v)
         for k, v in dict(r).items()}
        for r in rows
    ], "total": total}


@router.get("/leads/{lead_id}/calls")
async def lead_calls(lead_id: UUID, user: dict = Depends(current_user)):
    """Call history for one lead, newest first."""
    engine = neon_engine()
    if engine is None:
        return {"items": []}
    async with engine.connect() as conn:
        rows = (await conn.execute(
            select(CallLog.call_id, CallLog.leg, CallLog.direction, CallLog.status,
                   CallLog.agent_status, CallLog.answered, CallLog.start_at, CallLog.end_at)
            .where(CallLog.lead_id == lead_id)
            .order_by(desc(CallLog.start_at)).limit(50)
        )).mappings().all()
    return {"items": [
        {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(r).items()}
        for r in rows
    ]}
