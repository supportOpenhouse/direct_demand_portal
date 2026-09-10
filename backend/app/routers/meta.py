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

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

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
