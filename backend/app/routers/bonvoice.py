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
from datetime import datetime, timezone
from urllib.parse import parse_qsl
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import desc, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..core.auth import current_user
from ..db import neon_engine
from ..models import CallLog

log = logging.getLogger("bonvoice")
router = APIRouter(tags=["bonvoice"])

AUTOCALL_BRIDGE = "3"  # autocallType for a two-leg bridged call (4 = TTS, 5 = voicebot)
CALL_ANSWERED = "1"    # callType on the lifecycle callback

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
            f"{s.BONVOICE_BASE_URL.rstrip('/')}/usermanagement/external-auth/",
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

    event_id = uuid4().hex[:16]  # docs: unique alphanumeric, 8–16 chars
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
        "callBackParams": {"lead_id": str(req.lead_id), "actor": user.get("email")},
    }

    async def _post(tok: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=25.0) as client:
            return await client.post(
                f"{s.BONVOICE_BASE_URL.rstrip('/')}/autoDialManagement/autoCallBridging/",
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

    log.info("bonvoice call placed by=%s rm=%s lead=%s event=%s",
             user.get("email"), _mask(rm_phone), _mask(lead_phone), event_id)
    return {"status": "ringing", "event_id": event_id, "rm_phone_masked": _mask(rm_phone)}


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


async def _persist(body: dict) -> None:
    """Upsert the leg with only what this lifecycle event knows.

    Every field uses COALESCE precedence so a late 'initiated' can't blank the
    hangup's EndTime, and `answered` is OR-ed so it never flips back to false.
    """
    engine = neon_engine()
    call_id, leg = body.get("callID"), (body.get("Leg") or "A")
    if engine is None or not call_id:
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
        "recording_url": body.get("ResourceURL") or None,
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
