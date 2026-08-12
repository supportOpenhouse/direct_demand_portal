"""Huvo call-update webhook — the endpoint Huvo POSTs a completed call to.

Their integration note: "By default, we send the JSON payload without authentication,
and we do not generate a token." So the shared secret is ours to impose and ours to
hand them. `?token=` matches the Gupshup and Bonvoice callbacks — a vendor that
configures a URL and nothing else leaves no other channel — and an `X-Huvo-Token`
header is accepted too, so they can pick whichever their side supports.

Two deliberate refusals:

  * This does NOT touch the lead. The payload can say `not_interested` for a number
    whose lead is already `won`, and whether a vendor's bot may move a lead through
    the funnel is a product decision nobody has made. Landing the raw envelope keeps
    that decision open and re-derivable.

  * It does not fail on a payload it doesn't recognise. Their docs say a non-2xx tells
    Huvo the update was not accepted, and an update we've stored IS accepted — so
    anything short of "we couldn't store it" answers 200.
"""
import json
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from ..config import get_settings
from ..db import neon_engine
from ..services.huvo import extract

log = logging.getLogger("huvo")
router = APIRouter(tags=["huvo"])


def _secret() -> str:
    return (get_settings().HUVO_WEBHOOK_SECRET or "").strip()


def _is_prod() -> bool:
    return get_settings().is_prod


def check_token(token: str | None) -> None:
    """Shared-secret gate.

    Unset is open in dev so local testing needs no setup — same as the Gupshup
    callback. In prod that would be an unauthenticated public endpoint accepting call
    outcomes for arbitrary phone numbers, so there it refuses to serve at all rather
    than quietly accepting anything.
    """
    secret = _secret()
    if not secret:
        if _is_prod():
            log.error("HUVO_WEBHOOK_SECRET unset in prod — refusing to accept webhooks")
            raise HTTPException(
                status_code=503,
                detail="webhook not configured — set HUVO_WEBHOOK_SECRET",
            )
        return
    # constant-time: a plain == leaks the secret one character at a time to anyone
    # who can measure the response
    if not secrets.compare_digest(token or "", secret):
        raise HTTPException(status_code=403, detail="invalid token")


# The lead this number belongs to, if any. Deliberately last-10-digits, matching every
# other phone comparison in the app. ORDER BY: a number can belong to more than one
# lead (~5% here, the same buyer arriving from two portals), so prefer one that's
# still live over one already closed out, then the most recent.
_MATCH_LEAD = text("""
    SELECT id FROM leads
     WHERE phone IS NOT NULL
       AND right(regexp_replace(phone, '[^0-9]', '', 'g'), 10) = :p
     ORDER BY (stage IN ('won','rejected','rnr')), created_at DESC
     LIMIT 1
""")

_INSERT = text("""
    INSERT INTO huvo_call_updates
           (id, dedupe_key, lead_id, from_number, caller_name, call_outcome,
            is_interested, rsvp_status, lead_score, budget_lacs, summary,
            recording_url, duration_sec, started_at, ended_at, follow_up_at,
            payload, received_at)
    VALUES (gen_random_uuid(), :dedupe_key, :lead_id, :from_number, :caller_name,
            :call_outcome, :is_interested, :rsvp_status, :lead_score, :budget_lacs,
            :summary, :recording_url, :duration_sec, :started_at, :ended_at,
            :follow_up_at, CAST(:payload AS jsonb), now())
    -- their contract has no delivery id and no retry policy, so the same payload can
    -- and will arrive twice; a resend must not double-count the call
    ON CONFLICT (dedupe_key) DO NOTHING
    RETURNING id
""")


@router.post("/huvo/call-update")
async def huvo_call_update(request: Request):
    """Receive one completed call.

    Answers 200 with whether the row was stored or recognised as a duplicate. Huvo
    reads any 2xx as accepted, which both of those are.
    """
    check_token(request.query_params.get("token") or request.headers.get("x-huvo-token"))

    try:
        envelope = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="body must be JSON")
    if not isinstance(envelope, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")

    engine = neon_engine()
    if engine is None:
        # 503, not 200: we genuinely did not accept it, and a retry could succeed.
        raise HTTPException(status_code=503, detail="database not configured")

    row = extract(envelope)
    async with engine.begin() as conn:
        lead_id = None
        if row["from_number"]:
            lead_id = (await conn.execute(_MATCH_LEAD, {"p": row["from_number"]})).scalar()
        inserted = (await conn.execute(_INSERT, {
            **row, "lead_id": lead_id, "payload": json.dumps(envelope, default=str),
        })).scalar()

    if inserted is None:
        log.info("huvo: duplicate call update %s ignored", row["dedupe_key"])
        return {"status": "duplicate", "stored": False, "lead_matched": lead_id is not None}

    log.info("huvo: stored call update %s outcome=%s lead=%s",
             row["dedupe_key"], row["call_outcome"], lead_id)
    return {"status": "ok", "stored": True, "lead_matched": lead_id is not None}
