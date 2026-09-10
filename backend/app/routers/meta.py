"""Meta lead-ads webhook.

Meta's contract is two endpoints on one URL: a one-time GET handshake that echoes a
challenge, and POSTs carrying leadgen notifications. Both live here; everything with
a decision in it lives in `services/meta_leads.py`.

Auth is NOT the `?token=` this app uses for Huvo, Gupshup and Bonvoice — Meta does not
send a custom query param and cannot be asked to. The GET is gated by the verify token
Meta echoes, and every POST by an HMAC of the raw body under the app secret.

The POST answers 200 as soon as the deliveries are recorded, even when an individual
lead failed to process. A non-2xx tells Meta to resend the whole batch, which re-runs
the deliveries that already worked; a `failed` row is visible, retryable and does not
lie about what happened.
"""
import json
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from ..core.auth import require_admin
from ..db import neon_engine
from ..services.meta_leads import (
    check_signature,
    check_verify_token,
    leadgen_values,
    process_value,
)

log = logging.getLogger("meta")
router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/webhook", response_class=PlainTextResponse)
async def verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
):
    """Subscription handshake. Meta wants the raw challenge back as the whole body —
    a JSON-quoted string fails verification with no useful message."""
    check_verify_token(hub_verify_token)
    log.info("meta webhook handshake ok (mode=%s)", hub_mode)
    return PlainTextResponse(hub_challenge or "")


@router.post("/webhook")
async def receive(request: Request):
    """Leadgen notifications. One POST can carry several."""
    raw = await request.body()
    check_signature(raw, request.headers.get("X-Hub-Signature-256"))

    payload = json.loads(raw)
    values = leadgen_values(payload)
    if not values:
        # A Page subscribed to more than one field delivers those here too. Not an
        # error, and answering anything but 200 would make Meta retry it forever.
        log.info("meta webhook: no leadgen changes in payload")
        return {"status": "ok", "received": 0}

    statuses = [await process_value(value, payload) for value in values]
    return {
        "status": "ok",
        "received": len(statuses),
        "processed": statuses.count("success"),
        "duplicate": statuses.count("duplicate"),
        "failed": statuses.count("failed"),
    }


# Newest first, with the lead each delivery landed on.
#
# The join is on `origin_key`, not `leads.meta_lead_id`: that column only ever holds
# the FIRST delivery's id, so joining on it would show every repeat submission from
# the same buyer as an orphan.
LIST_EVENTS = text("""
    SELECT e.meta_lead_id, e.status, e.attempts, e.error_message,
           e.received_at, e.processed_at,
           e.page_id, e.form_id, e.campaign_id, e.campaign_name,
           e.adset_id, e.ad_id, e.ad_name, e.raw_lead,
           l.id AS lead_id, l.name AS lead_name, l.phone AS lead_phone,
           l.stage AS lead_stage, l.city AS lead_city, l.assigned_to AS lead_assigned_to
      FROM meta_lead_events e
      LEFT JOIN leads l ON l.origin_key = e.origin_key
     ORDER BY e.received_at DESC
     LIMIT :limit
""")


@router.get("/leads")
async def list_meta_leads(
    limit: int = Query(default=200, ge=1, le=1000),
    _: dict = Depends(require_admin),
):
    """Every webhook delivery and what became of it. Admin only.

    Returns the whole recent window in one go and lets the browser filter it — the
    volume is a few hundred rows, and paging a list this small buys nothing but two
    more states to get wrong.
    """
    engine = neon_engine()
    if engine is None:
        return {"status": "not_configured", "count": 0, "items": []}

    async with engine.begin() as conn:
        rows = (await conn.execute(LIST_EVENTS, {"limit": limit})).mappings().all()

    items = []
    for r in rows:
        raw = r["raw_lead"] or {}
        # The answers, in the order the form asked them. `flatten` would collapse to a
        # dict and lose that order, and a form reads wrong out of order.
        responses = [
            {"question": (f.get("name") or "").strip(),
             "answer": (f.get("values") or [""])[0]}
            for f in (raw.get("field_data") or [])
            if (f.get("name") or "").strip()
        ]
        items.append({
            "meta_lead_id": r["meta_lead_id"],
            "status": r["status"],
            "attempts": r["attempts"],
            "error_message": r["error_message"],
            "received_at": r["received_at"].isoformat() if r["received_at"] else None,
            "processed_at": r["processed_at"].isoformat() if r["processed_at"] else None,
            "created_time": raw.get("created_time"),
            "form_id": r["form_id"],
            "campaign_id": r["campaign_id"],
            "campaign_name": r["campaign_name"],
            "adset_id": r["adset_id"],
            "adset_name": raw.get("adset_name"),
            "ad_id": r["ad_id"],
            "ad_name": r["ad_name"],
            "responses": responses,
            "lead": {
                "id": str(r["lead_id"]),
                "name": r["lead_name"],
                "phone": r["lead_phone"],
                "stage": r["lead_stage"],
                "city": r["lead_city"],
                "assigned_to": r["lead_assigned_to"],
            } if r["lead_id"] else None,
        })
    return {"status": "ok", "count": len(items), "items": items}
