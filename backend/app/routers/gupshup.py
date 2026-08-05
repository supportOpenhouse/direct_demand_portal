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
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from urllib.parse import parse_qsl

from ..config import get_settings
# RMs may work the conversations assigned to them; admins see everything. The raw
# callback feed stays admin-only — it's a debugging surface, not a worklist.
from ..core.auth import assignment_aliases, current_user, require_admin
from ..db import neon_engine
from ..models import Lead, WaContact, WaMessage

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


def _media_of(inner: dict) -> dict:
    """Media columns from an inbound payload. Voice notes, images and documents all
    arrive as {url, contentType, urlExpiry} — the URL is a temporary Gupshup link, so
    urlExpiry is kept to tell "not sent" apart from "link has since expired"."""
    url = inner.get("url")
    if not url:
        return {}
    expiry = inner.get("urlExpiry")
    return {
        "media_url": url,
        "media_name": inner.get("name"),
        # urlExpiry is unix MILLIseconds
        "media_expiry": (datetime.fromtimestamp(expiry / 1000, timezone.utc)
                         if isinstance(expiry, (int, float)) else None),
    }


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
                    **_media_of(inner),
                ))
                # first message from this number → give the conversation an owner
                from ..services.wa_assign import assign_if_unassigned
                await assign_if_unassigned(conn, normalize_phone(
                    payload.get("sender", {}).get("phone") or payload.get("source"))[-10:])
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


async def _assert_owns(conn, user: dict, phone10: str) -> None:
    """An RM may only act on conversations assigned to them. Admins are unrestricted.
    Without this, opening the page to RMs would let any of them message any customer."""
    if user.get("role") != "rm":
        return
    aliases = assignment_aliases(user)
    owner = (await conn.execute(
        text("SELECT lower(assigned_to) FROM wa_contacts WHERE phone10 = :p"), {"p": phone10}
    )).first()
    if not aliases or not owner or not owner[0] or owner[0] not in aliases:
        raise HTTPException(status_code=403, detail="this conversation is assigned to someone else")


def _thread_scope(user: dict):
    """Which conversations this user may see, as a WaMessage predicate.

    RMs get the ones assigned to them; admins get everything. Matching goes through
    the same first-name/full-name aliases used for leads, so an RM's WhatsApp threads
    and their leads resolve identically."""
    if user.get("role") != "rm":
        return None
    aliases = assignment_aliases(user)
    if not aliases:
        return text("false")
    return func.right(WaMessage.phone, 10).in_(
        select(WaContact.phone10).where(func.lower(WaContact.assigned_to).in_(aliases))
    )


@router.get("/gupshup/messages")
async def gupshup_messages(phone: str | None = None, user: dict = Depends(current_user)):
    """Stored messages, newest first. The client groups by phone into threads — at this
    volume that's cheaper than a per-thread endpoint. Pass `phone` to narrow to one
    conversation (the lead-detail card); numbers are matched on their last 10 digits."""
    settings = get_settings()
    engine = neon_engine()
    if engine is None:
        return {"status": "not_configured", "send_enabled": False,
                "leads": {}, "tags": {}, "owners": {}, "items": []}
    q = select(
        WaMessage.id, WaMessage.direction, WaMessage.phone, WaMessage.name,
        WaMessage.body, WaMessage.msg_type, WaMessage.status, WaMessage.author,
        WaMessage.media_url, WaMessage.media_expiry, WaMessage.media_name,
        WaMessage.created_at,
    )
    scope = _thread_scope(user)
    if scope is not None:
        q = q.where(scope)
    if phone is not None:
        want = normalize_phone(phone)[-10:]
        if not want:
            return {"status": "ok", "send_enabled": settings.gupshup_send_configured,
                    "leads": {}, "tags": {}, "owners": {}, "items": []}
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

        # hand-applied marks (broker / buyer / seller / rejected), same phone10 key
        tags = {}
        if phones10:
            trows = (await conn.execute(
                select(WaContact.phone10, WaContact.tag, WaContact.assigned_to)
                .where(WaContact.phone10.in_(phones10))
            )).mappings().all()
            tags = {t["phone10"]: t["tag"] for t in trows if t["tag"]}
            owners = {t["phone10"]: t["assigned_to"] for t in trows if t["assigned_to"]}

    return {
        "status": "ok",
        "send_enabled": settings.gupshup_send_configured,
        "leads": leads,  # last-10-digits → the lead that already exists for it
        "tags": tags,    # last-10-digits → broker | buyer | seller | rejected
        "owners": owners,  # last-10-digits → the RM who owns the conversation
        "items": [dict(r) | {"id": str(r["id"])} for r in rows],
    }


WA_TAGS = ("broker", "buyer", "seller", "rejected")


class AssignRequest(BaseModel):
    phone: str
    assigned_to: str | None = None  # null unassigns; auto-assignment won't reclaim it


@router.post("/gupshup/assign", dependencies=[Depends(require_admin)])
async def gupshup_assign(req: AssignRequest):
    """Hand a conversation to a specific RM. Admin-only — an RM reassigning their own
    threads away would defeat the point of distributing them."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    phone10 = normalize_phone(req.phone)[-10:]
    if len(phone10) != 10:
        raise HTTPException(status_code=400, detail="invalid phone number")
    now = datetime.now(timezone.utc)
    stmt = pg_insert(WaContact).values(
        phone10=phone10, assigned_to=req.assigned_to, assigned_at=now,
    ).on_conflict_do_update(
        index_elements=[WaContact.phone10],
        set_={"assigned_to": req.assigned_to, "assigned_at": now},
    )
    async with engine.begin() as conn:
        await conn.execute(stmt)
    return {"status": "ok", "phone10": phone10, "assigned_to": req.assigned_to}


@router.post("/gupshup/assign/backfill", dependencies=[Depends(require_admin)])
async def gupshup_backfill():
    """Distribute every conversation that has no owner yet — for the threads that
    predate assignment. Safe to re-run; it only touches unowned, non-rejected ones."""
    from ..services.wa_assign import backfill

    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    async with engine.begin() as conn:
        assigned = await backfill(conn)
    return {"status": "ok", "assigned": assigned}


class MarkRequest(BaseModel):
    phone: str
    tag: Literal["broker", "buyer", "seller", "rejected"]


@router.post("/gupshup/mark")
async def gupshup_mark(req: MarkRequest, user: dict = Depends(require_admin)):
    """Mark what a number turned out to be. Re-marking overwrites the previous value."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    phone10 = normalize_phone(req.phone)[-10:]
    if len(phone10) != 10:
        raise HTTPException(status_code=400, detail="invalid phone number")
    marked_by = user.get("name") or user.get("email")
    now = datetime.now(timezone.utc)
    # a rejected number stops consuming an RM's share, so its owner is cleared
    rejected = req.tag == "rejected"
    values = {"tag": req.tag, "marked_by": marked_by, "marked_at": now}
    if rejected:
        values |= {"assigned_to": None, "assigned_at": None}
    stmt = pg_insert(WaContact).values(phone10=phone10, **values).on_conflict_do_update(
        index_elements=[WaContact.phone10], set_=values,
    )
    async with engine.begin() as conn:
        await conn.execute(stmt)
        if not rejected:  # un-rejecting puts it back into the rotation
            from ..services.wa_assign import assign_if_unassigned
            await assign_if_unassigned(conn, phone10)
    log.info("gupshup mark %s%s as %s by %s", "•" * 6, phone10[-4:], req.tag, marked_by)
    return {"status": "ok", "phone10": phone10, "tag": req.tag}


@router.get("/gupshup/latest")
async def gupshup_latest(user: dict = Depends(current_user)):
    """Timestamp of the newest inbound message — one indexed MAX(), cheap enough for
    the topbar to poll from every page. The client compares it against the last time
    this browser opened the WhatsApp page to decide whether to show the dot."""
    engine = neon_engine()
    if engine is None:
        return {"last_inbound_at": None}
    async with engine.connect() as conn:
        q = select(func.max(WaMessage.created_at)).where(WaMessage.direction == "in")
        scope = _thread_scope(user)
        if scope is not None:
            q = q.where(scope)
        row = (await conn.execute(q)).first()
    return {"last_inbound_at": row[0].isoformat() if row and row[0] else None}


class CreateLeadRequest(BaseModel):
    phone: str
    name: str = Field(min_length=1, max_length=120)
    city: str | None = None
    society: str | None = None


@router.post("/gupshup/leads")
async def gupshup_create_lead(req: CreateLeadRequest, user: dict = Depends(current_user)):
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
        await _assert_owns(conn, user, phone10)
        await conn.execute(
            pg_insert(Lead).values(values).on_conflict_do_nothing(index_elements=["origin_key"])
        )
        row = (await conn.execute(
            select(Lead.id).where(Lead.origin_key == values["origin_key"])
        )).first()
    return {"status": "ok", "lead_id": str(row[0]) if row else None}


class BulkLeadRequest(BaseModel):
    # capped so one click can't fan out into an unbounded write
    phones: list[str] = Field(min_length=1, max_length=500)


@router.post("/gupshup/leads/bulk")
async def gupshup_bulk_create_leads(req: BulkLeadRequest, user: dict = Depends(current_user)):
    """Create spine leads from many WhatsApp conversations in one go.

    Each lead inherits the conversation's owning RM — a WhatsApp lead that lands
    unassigned is invisible to the RM already talking to that person.

    The name is taken server-side from the latest inbound WhatsApp profile name
    rather than the client's list, so a stale browser can't stamp the wrong name on
    a lead. Idempotent on origin_key exactly like the single-lead endpoint, so
    contacts that already have a lead are counted as skipped, never duplicated.
    """
    from ..services.leads_sync import TAT_HOURS, display_phone, norm_phone

    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")

    # dedupe: the same conversation can't be selected twice
    phones10 = sorted({p10 for p10 in (norm_phone(p) for p in req.phones) if p10 and len(p10) == 10})
    if not phones10:
        raise HTTPException(status_code=400, detail="no valid phone numbers")

    now = datetime.now(timezone.utc)
    async with engine.begin() as conn:
        contacts = {r["phone10"]: r["assigned_to"] for r in (await conn.execute(
            text("SELECT phone10, assigned_to FROM wa_contacts WHERE phone10 = ANY(:ps)"),
            {"ps": phones10},
        )).mappings()}

        # One ownership check for the whole batch instead of per phone. Same rule as
        # _assert_owns: an RM may only act on their own conversations.
        if user.get("role") == "rm":
            aliases = assignment_aliases(user)
            foreign = [p for p in phones10
                       if not aliases or (contacts.get(p) or "").lower() not in aliases]
            if foreign:
                raise HTTPException(
                    status_code=403,
                    detail=f"{len(foreign)} of these conversations are assigned to someone else")

        # newest inbound profile name per contact; DISTINCT ON needs the same leading
        # ORDER BY key, hence phone10 first
        names = {r["p10"]: r["name"] for r in (await conn.execute(
            text("""SELECT DISTINCT ON (right(regexp_replace(phone, '\\D', '', 'g'), 10))
                           right(regexp_replace(phone, '\\D', '', 'g'), 10) AS p10, name
                      FROM wa_messages
                     WHERE direction = 'inbound' AND name IS NOT NULL AND btrim(name) <> ''
                       AND right(regexp_replace(phone, '\\D', '', 'g'), 10) = ANY(:ps)
                     ORDER BY 1, created_at DESC"""),
            {"ps": phones10},
        )).mappings()}

        keys = [f"whatsapp:{p}" for p in phones10]
        already = {r[0] for r in (await conn.execute(
            text("SELECT origin_key FROM leads WHERE origin_key = ANY(:ks)"), {"ks": keys})).all()}

        rows = [{
            "origin_key": f"whatsapp:{p}", "source_category": "whatsapp", "source": "whatsapp",
            "name": (names.get(p) or "").strip() or display_phone(p),
            "phone": display_phone(p),
            # the whole point: the conversation's RM owns the lead too
            "assigned_to": contacts.get(p),
            "received_at": now, "tat_deadline": now + timedelta(hours=TAT_HOURS),
            "source_meta": {"created_from": "whatsapp_bulk", "created_by": user.get("email")},
        } for p in phones10 if f"whatsapp:{p}" not in already]

        if rows:
            await conn.execute(
                pg_insert(Lead).on_conflict_do_nothing(index_elements=["origin_key"]), rows)

    unassigned = sum(1 for r in rows if not r["assigned_to"])
    log.info("whatsapp: bulk-created %d leads (%d already existed, %d unassigned) by %s",
             len(rows), len(already), unassigned, user.get("email"))
    return {"status": "ok", "created": len(rows), "skipped_existing": len(already),
            "unassigned": unassigned, "requested": len(phones10)}


class SendRequest(BaseModel):
    phone: str
    text: str = Field(min_length=1, max_length=4096)


@router.post("/gupshup/send")
async def gupshup_send(req: SendRequest, user: dict = Depends(current_user)):
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
    engine = neon_engine()
    if engine is not None:
        async with engine.connect() as conn:
            await _assert_owns(conn, user, destination[-10:])

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

    # display name, falling back to email — this is what the chat shows under the
    # bubble. The audit log separately records the actor's email.
    author = user.get("name") or user.get("email")
    # masked so an outbound log line never carries a full customer number
    log.info("gupshup send by=%s to=%s%s id=%s",
             author, "•" * max(0, len(destination) - 4), destination[-4:], gupshup_id)

    engine = neon_engine()
    if engine is not None:
        async with engine.begin() as conn:
            await conn.execute(WaMessage.__table__.insert().values(
                direction="out", phone=destination, body=req.text, msg_type="text",
                gupshup_id=gupshup_id, status="submitted", author=author,
            ))
    return {"status": "sent", "gupshup_id": gupshup_id, "author": author}
