"""Gupshup WhatsApp — inbound callback, persistence, and outbound send.

Receiving needs no config at all. Sending needs GUPSHUP_API_KEY + _SOURCE_NUMBER +
_APP_NAME; without them /send reports "not configured" rather than failing obscurely.

The callback must answer 2xx with an empty body inside 10s (Gupshup retries, then
disables the URL), so the handler only appends to an in-memory ring and hands the DB
write to a background task — the same fire-and-forget shape the audit middleware uses.

The 24-hour rule is WhatsApp's, not Gupshup's: free-form text only reaches a customer
within 24h of THEIR last message. Outside it, only pre-approved templates. This module
records the window; refusing the send is left to the UI and, ultimately, to Gupshup.
"""
import asyncio
import json
import logging
import re
import secrets
from collections import deque
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from urllib.parse import parse_qsl

from ..config import get_settings
# admin-only for now: reading a whole customer thread and messaging as the business
# are both wider than an RM's remit. Widen deliberately, not by default.
from ..core.auth import require_admin
from ..db import neon_engine
from ..models import Lead, WaMessage

log = logging.getLogger("gupshup")
router = APIRouter(tags=["gupshup"])

SEND_URL = "https://api.gupshup.io/wa/api/v1/msg"
THREAD_LIMIT = 500  # ponytail: one flat fetch, grouped client-side. Paginate if it bites.

# ponytail: raw-callback ring for reading shapes that aren't modelled yet (billing,
# system events). The conversation itself lives in wa_messages, not here.
_RECENT: deque[dict] = deque(maxlen=50)


def normalize_phone(phone: str | None) -> str:
    """Digits only, with India's country code added to a bare 10-digit mobile —
    Gupshup addresses everyone in full international form."""
    d = re.sub(r"\D", "", phone or "")
    return "91" + d if len(d) == 10 else d


def parse_body(raw: bytes, content_type: str) -> dict | list | str:
    """Gupshup sends JSON on the WhatsApp callback and form-encoded on some of the
    older ones. Return whichever parses; fall back to the raw text so an unexpected
    format still shows up in /recent instead of vanishing."""
    body = raw.decode("utf-8", "replace")
    if not body:
        return {}
    if "form-urlencoded" in content_type:
        return dict(parse_qsl(body))
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def _check_token(request: Request) -> None:
    """Optional shared secret via ?token= — Gupshup's dashboard only accepts a URL,
    so a query param is the only channel available. Unset = open (dev)."""
    secret = get_settings().GUPSHUP_WEBHOOK_SECRET.strip()
    if secret and not secrets.compare_digest(request.query_params.get("token", ""), secret):
        raise HTTPException(status_code=403, detail="invalid token")


def _text_of(inner: dict, kind: str | None) -> str | None:
    """Readable body for the thread — the text itself, or a caption/label for media."""
    if kind == "text":
        return inner.get("text")
    if kind == "location":
        return inner.get("name") or inner.get("address")
    return inner.get("caption") or None


async def _persist(entry: dict) -> None:
    """Write an inbound message, or apply a delivery event to the row it belongs to.
    Fire-and-forget: a DB blip must never affect the callback's 200."""
    engine = neon_engine()
    if engine is None:
        return
    body = entry.get("body")
    if not isinstance(body, dict):
        return
    payload = body.get("payload") or {}
    try:
        if entry["type"] == "message":
            inner = payload.get("payload") or {}
            kind = payload.get("type")
            async with engine.begin() as conn:
                await conn.execute(WaMessage.__table__.insert().values(
                    direction="in",
                    phone=normalize_phone(payload.get("sender", {}).get("phone") or payload.get("source")),
                    name=payload.get("sender", {}).get("name"),
                    body=_text_of(inner, kind),
                    msg_type=kind or "text",
                    gupshup_id=payload.get("id"),
                    raw=body,
                ))
        elif entry["type"] == "message-event" and payload.get("id"):
            # delivery receipts arrive minutes later, keyed by the id /send stored
            async with engine.begin() as conn:
                await conn.execute(
                    update(WaMessage)
                    .where(WaMessage.gupshup_id == payload["id"])
                    .values(status=payload.get("type"))
                )
    except Exception:  # noqa: BLE001 — logging only; the callback already answered 200
        log.exception("gupshup: failed to persist callback")


@router.get("/gupshup/webhook")
async def gupshup_verify(request: Request):
    """Smoke-test / verification hit — Gupshup and browsers both GET the URL first."""
    _check_token(request)
    return {"status": "ok"}


@router.post("/gupshup/webhook", status_code=200, response_class=Response)
async def gupshup_webhook(request: Request):
    """Gupshup wants 2xx with an EMPTY body inside 10s (<500ms recommended), or it
    retries and eventually disables the callback. Nothing here blocks on I/O."""
    _check_token(request)
    try:
        body = parse_body(await request.body(), request.headers.get("content-type", ""))
    except Exception:  # noqa: BLE001 — a 500 here makes Gupshup disable the callback
        log.exception("gupshup: unreadable callback body")
        return Response(status_code=200)

    entry = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "type": body.get("type") if isinstance(body, dict) else None,
        "body": body,
    }
    _RECENT.appendleft(entry)
    log.info("gupshup callback type=%s body=%s", entry["type"], json.dumps(body, default=str)[:2000])
    asyncio.create_task(_persist(entry))
    return Response(status_code=200)


@router.get("/gupshup/recent", dependencies=[Depends(require_admin)])
async def gupshup_recent():
    """The last 50 raw callbacks, newest first — for shapes wa_messages doesn't model."""
    return {"count": len(_RECENT), "items": list(_RECENT)}


@router.get("/gupshup/messages")
async def gupshup_messages(phone: str | None = None, user: dict = Depends(require_admin)):
    """Stored messages, newest first. The client groups by phone into threads — at this
    volume that's cheaper than a per-thread endpoint. Pass `phone` to narrow to one
    conversation (the lead-detail card); numbers are matched on their last 10 digits."""
    settings = get_settings()
    engine = neon_engine()
    if engine is None:
        return {"status": "not_configured", "send_enabled": False, "leads": {}, "items": []}
    q = select(
        WaMessage.id, WaMessage.direction, WaMessage.phone, WaMessage.name,
        WaMessage.body, WaMessage.msg_type, WaMessage.status, WaMessage.author,
        WaMessage.created_at,
    )
    if phone is not None:
        want = normalize_phone(phone)[-10:]
        if not want:
            return {"status": "ok", "send_enabled": settings.gupshup_send_configured,
                    "leads": {}, "items": []}
        q = q.where(func.right(WaMessage.phone, 10) == want)
    async with engine.connect() as conn:
        rows = (await conn.execute(
            q.order_by(desc(WaMessage.created_at)).limit(THREAD_LIMIT)
        )).mappings().all()

        # which of these numbers already have a lead. Leads store a formatted phone
        # ("+91 98715 78484") while WhatsApp gives "919871578484", so both sides are
        # reduced to the last 10 digits — the same key leads_sync dedupes on.
        phones10 = sorted({r["phone"][-10:] for r in rows if r["phone"]})
        leads = {}
        if phones10:
            p10 = func.right(func.regexp_replace(Lead.phone, r"\D", "", "g"), 10)
            found = (await conn.execute(
                select(Lead.id, Lead.name, p10.label("p10")).where(p10.in_(phones10))
            )).mappings().all()
            leads = {f["p10"]: {"id": str(f["id"]), "name": f["name"]} for f in found}

    return {
        "status": "ok",
        "send_enabled": settings.gupshup_send_configured,
        "leads": leads,  # last-10-digits → the lead that already exists for it
        "items": [dict(r) | {"id": str(r["id"])} for r in rows],
    }


class CreateLeadRequest(BaseModel):
    phone: str
    name: str = Field(min_length=1, max_length=120)
    city: str | None = None
    society: str | None = None


@router.post("/gupshup/leads")
async def gupshup_create_lead(req: CreateLeadRequest, user: dict = Depends(require_admin)):
    """Create a spine lead from a WhatsApp conversation. Idempotent on origin_key, so
    a double-click returns the existing lead rather than a duplicate."""
    from ..services.leads_sync import TAT_HOURS, display_phone, norm_phone

    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    phone10 = norm_phone(req.phone)
    if not phone10 or len(phone10) != 10:
        raise HTTPException(status_code=400, detail="invalid phone number")

    now = datetime.now(timezone.utc)
    city = (req.city or "").strip() or None
    society = (req.society or "").strip() or None
    values = {
        "origin_key": f"whatsapp:{phone10}", "source_category": "whatsapp", "source": "whatsapp",
        "name": req.name.strip(), "phone": display_phone(phone10), "city": city, "society": society,
        "received_at": now, "tat_deadline": now + timedelta(hours=TAT_HOURS),
        "source_meta": {"created_from": "whatsapp_chat", "created_by": user.get("email")},
    }
    async with engine.begin() as conn:
        await conn.execute(
            pg_insert(Lead).values(values).on_conflict_do_nothing(index_elements=["origin_key"])
        )
        row = (await conn.execute(
            select(Lead.id).where(Lead.origin_key == values["origin_key"])
        )).first()
    return {"status": "ok", "lead_id": str(row[0]) if row else None}


class SendRequest(BaseModel):
    phone: str
    text: str = Field(min_length=1, max_length=4096)


@router.post("/gupshup/send")
async def gupshup_send(req: SendRequest, user: dict = Depends(require_admin)):
    settings = get_settings()
    if not settings.gupshup_send_configured:
        raise HTTPException(
            status_code=503,
            detail="Sending isn't configured — set GUPSHUP_API_KEY, GUPSHUP_SOURCE_NUMBER "
                   "and GUPSHUP_APP_NAME.",
        )
    destination = normalize_phone(req.phone)
    if len(destination) < 10:
        raise HTTPException(status_code=400, detail="invalid phone number")

    form = {
        "channel": "whatsapp",
        "source": settings.GUPSHUP_SOURCE_NUMBER,
        "destination": destination,
        "src.name": settings.GUPSHUP_APP_NAME,
        "message": json.dumps({"type": "text", "text": req.text}),
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                SEND_URL, data=form,
                headers={"apikey": settings.GUPSHUP_API_KEY,
                         "Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as e:
        log.warning("gupshup send failed: %s", e)
        raise HTTPException(status_code=502, detail=f"couldn't reach Gupshup: {e}")

    detail = r.text[:300]
    if r.status_code >= 300:
        # the usual cause is the 24-hour window having closed — Gupshup says so here
        log.warning("gupshup send rejected (%s): %s", r.status_code, detail)
        raise HTTPException(status_code=502, detail=f"Gupshup rejected the message: {detail}")

    try:
        gupshup_id = r.json().get("messageId")
    except Exception:  # noqa: BLE001 — a 2xx without parseable JSON still means sent
        gupshup_id = None

    engine = neon_engine()
    if engine is not None:
        async with engine.begin() as conn:
            await conn.execute(WaMessage.__table__.insert().values(
                direction="out", phone=destination, body=req.text, msg_type="text",
                gupshup_id=gupshup_id, status="submitted", author=user.get("email"),
            ))
    return {"status": "sent", "gupshup_id": gupshup_id}
