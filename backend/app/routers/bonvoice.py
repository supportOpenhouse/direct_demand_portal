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
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import desc, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..core.auth import current_user, require_admin
from ..db import neon_engine
from ..models import CallLog, Lead, User

log = logging.getLogger("bonvoice")
router = APIRouter(tags=["bonvoice"])

IST = timezone(timedelta(hours=5, minutes=30))  # the PBX reports local time, unlabelled
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
    # call_logs is what /crm/callrecords/ actually uses (alongside a call_count)
    for key in ("call_logs", "callLogs", "data", "result", "results", "records", "logs", "calls"):
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


def _records_base() -> str:
    """The call-record API only answers on the `backend.` host — the bare pbx host
    that click-to-call uses returns nginx's 405 for it. Derived rather than configured
    so one BONVOICE_BASE_URL keeps working for both."""
    base = get_settings().bonvoice_base
    return base if "//backend." in base else base.replace("//", "//backend.", 1)


def _pbx_dt(value) -> datetime | None:
    """Timestamps come back as '2026-08-04 11:04:51 AM' — 12-hour, no timezone, and
    Indian local time. Naive would land in the DB as UTC and read 5½ hours early."""
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d %I:%M:%S %p").replace(tzinfo=IST)
    except (ValueError, TypeError):
        return _dt(value)


def _duration_secs(value) -> int | None:
    """'0 min 0sec' / '3 min 12 sec' → seconds. There's no EndTime in a pulled record,
    so this is the only way to know when the call finished."""
    m = re.search(r"(?:(\d+)\s*min)?\s*(?:(\d+)\s*sec)?", str(value or ""))
    if not m or not (m.group(1) or m.group(2)):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


async def fetch_call_records(date_from: str, date_to: str, agent: str | None = None) -> list[dict]:
    """Every call record Bonvoice holds for a date range — POST /crm/callrecords/.

    `agent` narrows it to one extension; omitted, the account's whole history comes
    back. Dates are plain YYYY-MM-DD, as in their docs.
    """
    payload = {"from": date_from, "to": date_to}
    if agent:
        payload["agent"] = agent
    url = f"{_records_base()}/crm/callrecords/"

    async def _post(tok: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=90.0) as client:
            return await client.post(url, json=payload,
                                     headers={"Authorization": f"Token {tok}"})

    r = await _post(await _auth_token())
    if r.status_code == 401:
        r = await _post(await _auth_token(force=True))
    if r.status_code >= 300:
        raise HTTPException(status_code=502,
                            detail=f"Bonvoice call records failed ({r.status_code}): {r.text[:200]}")
    try:
        body = r.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Bonvoice returned a non-JSON call-record list")
    records = log_records(body)
    if not records:
        # Once per empty pull: the only way to see an unexpected envelope without a
        # live account is to log the raw body.
        log.info("bonvoice: no call records parsed for %s..%s — raw: %s",
                 date_from, date_to, r.text[:600])
    return records


def record_to_callback(rec: dict) -> dict:
    """Reshape one /crm/callrecords/ row into the callback shape `_persist` upserts.

    A pulled record is one row per *conversation*, not per leg, and it names the two
    parties as Customer (the other person) and DisplayNumber (our DID) rather than
    source/destination — so which is which depends on CallDirection. It carries no
    lifecycle callType and no EndTime either: connectedness comes off the status text,
    and the end is start + CallDuration.

    Unmapped fields ride along untouched and land in `raw`.
    """
    _, answered, status = read_call_state([rec])
    customer = _field(rec, "Customer", "SourceNumber", "DestinationNumber")
    did = _field(rec, "DisplayNumber", "did")
    direction = str(_field(rec, "CallDirection", "Direction", "direction") or "")
    inbound = direction.lower().startswith("in")
    start = _pbx_dt(_field(rec, "StartTime", "startTime", "start_time", "callDate"))
    secs = _duration_secs(_field(rec, "CallDuration", "Duration"))
    end = _pbx_dt(_field(rec, "EndTime", "endTime", "end_time"))
    if end is None and start and secs is not None:
        end = start + timedelta(seconds=secs)
    return {**rec,
            "callID": _field(rec, "callID", "call_id", "uniqueid", "uniqueId"),
            # records don't split legs; 'A' merges with the caller leg a callback wrote
            "Leg": _field(rec, "Leg", "leg") or "A",
            "eventID": _field(rec, "eventID", "event_id"),
            "callBackParams": _field(rec, "callBackParams", "callback_params"),
            "Direction": direction or None,
            "SourceNumber": customer if inbound else did,
            "DestinationNumber": did if inbound else customer,
            "DisplayNumber": did,
            "Status": status or _field(rec, "Status", "callStatus", "disposition"),
            "AgentStatus": _field(rec, "AgentStatus", "agentStatus", "Agent"),
            # synthesised: `answered` is OR-ed into the row, so a false here can never
            # unset what a live callback already recorded
            "callType": CALL_ANSWERED if answered else "",
            "StartTime": start.isoformat() if start else None,
            "EndTime": end.isoformat() if end else None,
            # their field for the recording is CallRecord; the callback calls it
            # ResourceURL. A zero-second call gets a url too, but fetching it answers
            # "File not exist" — so drop it rather than hand the page a dead player.
            "ResourceURL": None if secs == 0 else
                _field(rec, "CallRecord", "ResourceURL", "recordingURL", "recording_url"),
            }


async def attach_lead_and_actor(mapped: list[dict]) -> int:
    """Fill in `callBackParams` for pulled records, which carry only phone numbers.

    A call placed from the portal comes back with its lead id echoed; one pulled from
    the record API doesn't, so the lead is found by number instead — Customer against
    leads.phone, Agent against users.phone, both compared on their last 10 digits.
    Returns how many records got a lead.
    """
    engine = neon_engine()
    if engine is None:
        return 0
    customers = {p for p in (_digits(m.get("Customer")) for m in mapped) if p}
    agents = {p for p in (_digits(m.get("Agent")) for m in mapped) if p}
    leads: dict[str, str] = {}
    users: dict[str, str] = {}
    async with engine.connect() as conn:
        if customers:
            p10 = func.right(func.regexp_replace(Lead.phone, r"\D", "", "g"), 10)
            rows = (await conn.execute(
                select(p10.label("p10"), Lead.id).where(p10.in_(sorted(customers)))
                # oldest first, so the newest lead on a repeated number wins the key
                .order_by(Lead.created_at)
            )).mappings().all()
            leads = {r["p10"]: str(r["id"]) for r in rows}
        if agents:
            u10 = func.right(func.regexp_replace(User.phone, r"\D", "", "g"), 10)
            rows = (await conn.execute(
                select(u10.label("p10"), User.email).where(u10.in_(sorted(agents)))
            )).mappings().all()
            users = {r["p10"]: r["email"] for r in rows}

    linked = 0
    for m in mapped:
        found = {}
        lead_id = leads.get(_digits(m.get("Customer")))
        actor = users.get(_digits(m.get("Agent")))
        if lead_id:
            found["lead_id"] = lead_id
            linked += 1
        if actor:
            found["actor"] = actor
        if not found:
            continue
        existing = m.get("callBackParams")
        # an echoed lead id came from the call itself — never overwrite it with a guess
        m["callBackParams"] = {**found, **existing} if isinstance(existing, dict) else found
    return linked


@router.post("/bonvoice/calls/sync", dependencies=[Depends(require_admin)])
async def sync_call_records(
    date_from: str = Query(..., alias="from"),   # YYYY-MM-DD
    date_to: str = Query(..., alias="to"),
    agent: str | None = Query(None),             # one extension, or all of them
):
    """Backfill the call log from Bonvoice for a date range.

    The webhook only ever reports calls placed after it was wired up; this pulls in
    everything else — history, calls placed from a handset, anything a dropped
    callback lost.
    """
    if not get_settings().bonvoice_configured:
        raise HTTPException(status_code=503, detail="Bonvoice isn't configured.")
    records = await fetch_call_records(date_from, date_to, agent)
    mapped = [m for m in (record_to_callback(r) for r in records) if m["callID"]]
    linked = await attach_lead_and_actor(mapped)
    # ponytail: one upsert per record, sequentially. A month is ~150 round trips on an
    # admin-triggered button — batch it if a wider range ever gets slow.
    for m in mapped:
        await _persist(m)
    log.info("bonvoice: synced %s/%s call records (%s linked to leads) for %s..%s",
             len(mapped), len(records), linked, date_from, date_to)
    return {"fetched": len(records), "stored": len(mapped), "linked": linked}


@router.post("/bonvoice/calls/repair-missing", dependencies=[Depends(require_admin)])
async def repair_missing_numbers(
    max_days: int = Query(60, ge=1, le=365),
    dry_run: bool = Query(False),
):
    """Re-pull Bonvoice's records for the days holding call_logs rows with no
    source_number, and upsert them over the gaps.

    A leg only learns its numbers from the callback that carried them. If that one
    delivery was dropped, a later lifecycle event still creates the row — with
    source_number NULL — and nothing ever goes back for it. `_persist` writes every
    field as COALESCE(EXCLUDED, existing), so re-pulling fills the hole and cannot
    overwrite anything already good.

    Scoped to the days that actually have holes rather than one min..max range:
    a handful of NULLs months apart would otherwise re-pull the whole history, one
    sequential upsert per record.

    Rows whose start_at is NULL too are dated by created_at — when we first stored
    them, which is within minutes of the call.
    """
    if not get_settings().bonvoice_configured:
        raise HTTPException(status_code=503, detail="Bonvoice isn't configured.")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")

    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT count(*) FROM call_logs WHERE source_number IS NULL"))).scalar() or 0
        days = [str(r[0]) for r in (await conn.execute(text("""
            SELECT DISTINCT (COALESCE(start_at, created_at) AT TIME ZONE 'Asia/Kolkata')::date AS d
              FROM call_logs
             WHERE source_number IS NULL
               AND COALESCE(start_at, created_at) IS NOT NULL
             ORDER BY d DESC"""))).all()]

    truncated = len(days) > max_days
    days = days[:max_days]  # newest first, so a cap keeps the most useful days
    if dry_run or not days:
        return {"missing_before": before, "days": days, "truncated": truncated,
                "fetched": 0, "stored": 0, "linked": 0, "missing_after": before,
                "dry_run": dry_run}

    fetched = stored = linked = 0
    for day in days:
        try:
            records = await fetch_call_records(day, day)
        except HTTPException:
            log.exception("bonvoice: repair pull failed for %s — skipping that day", day)
            continue  # one bad day must not abandon the rest
        mapped = [m for m in (record_to_callback(r) for r in records) if m["callID"]]
        linked += await attach_lead_and_actor(mapped)
        for m in mapped:
            await _persist(m)
        fetched += len(records)
        stored += len(mapped)

    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT count(*) FROM call_logs WHERE source_number IS NULL"))).scalar() or 0
    log.info("bonvoice: repaired %d/%d rows missing source_number across %d day(s)",
             before - after, before, len(days))
    return {"missing_before": before, "days": days, "truncated": truncated,
            "fetched": fetched, "stored": stored, "linked": linked,
            "missing_after": after, "repaired": before - after, "dry_run": False}


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
    try:
        async with engine.begin() as conn:
            # Attribute the call to the campaign that placed it, while the queue row
            # still carries this event_id — a retry clears it minutes later and the
            # link would be unrecoverable. NULL for manual click-to-call, and COALESCE
            # below means a later callback for the same leg can't blank it.
            if values["event_id"]:
                owner = (await conn.execute(text(
                    "SELECT campaign_id FROM dial_queue WHERE event_id = :ev LIMIT 1"),
                    {"ev": values["event_id"]})).first()
                if owner:
                    values["campaign_id"] = owner[0]
            stmt = pg_insert(CallLog).values(**values)
            updates = {k: text(f"COALESCE(EXCLUDED.{k}, call_logs.{k})")
                       for k in values if k not in ("call_id", "leg", "answered")}
            updates["answered"] = text("call_logs.answered OR EXCLUDED.answered")
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


def _p10_sql(col: str) -> str:
    """The last 10 digits of a phone column — the one key every format agrees on.
    Bonvoice reports '9220633844', users.phone holds '919999999999' and leads.phone
    '+91 99997 99588'; all three reduce to the same 10 digits."""
    return rf"right(regexp_replace(coalesce({col}, ''), '\D', '', 'g'), 10)"


def call_log_filters(q: str | None, answered: bool | None,
                     campaign_id: UUID | None = None) -> tuple[str, dict]:
    """WHERE clause + bind params for the call-log list. Split out so the same clause
    drives both the page and its count, and so it's testable without a database."""
    where, params = [], {}
    if campaign_id is not None:
        # Previous Campaigns reuses this endpoint rather than running its own query,
        # so a campaign's calls render in exactly the same shape as the Call Log page.
        where.append("c.campaign_id = :campaign_id")
        params["campaign_id"] = campaign_id
    if q:
        parts = ["c.source_number ILIKE :q", "c.destination_number ILIKE :q",
                 "c.display_number ILIKE :q", "l.name ILIKE :q"]
        params["q"] = f"%{q}%"
        # a search that's really a phone number matches on digits, so pasting
        # '+91 99997 99588', '919999799588' or '9999799588' all find the same calls
        q10 = _digits(q)
        if q10:
            parts += [f"{_p10_sql(c)} = :q10" for c in
                      ("c.source_number", "c.destination_number", "c.display_number", "l.phone")]
            params["q10"] = q10
        where.append("(" + " OR ".join(parts) + ")")
    if answered is not None:
        where.append("c.answered = :answered")
        params["answered"] = answered
    return (" WHERE " + " AND ".join(where)) if where else "", params


@router.get("/bonvoice/calls", dependencies=[Depends(require_admin)])
async def call_log(
    q: str | None = Query(None),          # matches any phone number or the lead's name
    answered: bool | None = Query(None),
    campaign_id: UUID | None = Query(None),  # only calls one auto-dialer campaign placed
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
    clause, params = call_log_filters(q, answered, campaign_id)
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
                   CallLog.agent_status, CallLog.answered, CallLog.start_at, CallLog.end_at,
                   CallLog.recording_url)
            .where(CallLog.lead_id == lead_id)
            .order_by(desc(CallLog.start_at)).limit(50)
        )).mappings().all()
    return {"items": [
        {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(r).items()}
        for r in rows
    ]}
