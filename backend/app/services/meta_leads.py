"""Meta lead ads -> the ingest the sheet already uses.

Meta posts a NOTIFICATION, not a lead: `leadgen_id` and little else worth having.
The lead itself is a second call to the Graph API with the system-user token.

Two keys, two jobs, and not confusing them is the whole design:

  * `meta_lead_events.meta_lead_id` (= leadgen_id) is DELIVERY idempotency. Meta
    retries; a retry must not run the ingest twice.
  * `leads.origin_key` (= meta:<phone10>) stays LEAD identity, unchanged from the
    4-hourly cron and the Apps Script. The same buyer arriving by sheet AND by
    webhook is one lead — which is what makes running both during cutover free.

Nothing here transforms a lead. `field_data` is flattened to {name: value} and handed
to `ingest_meta_rows`, because Meta's own Instant Form field names (`full_name`,
`phone_number`, `email`, `zip_code`, `your_budget_range`, ...) are exactly what
`build_meta` already reads — that is *why* the sheet's headers match them. Inventing a
second transform here would be a second definition of what a Meta lead is.
"""
import hashlib
import hmac
import json
import logging

import httpx
from fastapi import HTTPException
from sqlalchemy import text

from ..config import get_settings
from ..db import neon_engine
from .leads_sync import ingest_meta_rows, norm_phone

log = logging.getLogger("meta_leads")

# Everything the funnel needs. `field_data` is the lead; the rest is attribution.
LEAD_FIELDS = (
    "id,created_time,field_data,form_id,ad_id,ad_name,"
    "adset_id,adset_name,campaign_id,campaign_name"
)


# ---- auth ---------------------------------------------------------------------


def check_signature(raw_body: bytes, header: str | None) -> None:
    """`X-Hub-Signature-256` = 'sha256=' + HMAC-SHA256(raw body, app secret).

    Computed over the RAW bytes on purpose: re-serialising the parsed JSON changes key
    order and whitespace, and the digest stops matching for reasons that look nothing
    like the cause.

    Unset secret is open in dev so a local curl needs no setup — same rule as the Huvo
    and Gupshup callbacks. In prod that would be a public endpoint that inserts leads,
    so there it refuses to serve at all rather than accept anything.
    """
    settings = get_settings()
    secret = (settings.META_APP_SECRET or "").strip()
    if not secret:
        if settings.is_prod:
            log.error("META_APP_SECRET unset in prod — refusing to accept webhooks")
            raise HTTPException(
                status_code=503,
                detail="webhook not configured — set META_APP_SECRET",
            )
        return
    if not header or not header.startswith("sha256="):
        raise HTTPException(status_code=403, detail="invalid signature")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    # constant-time: a plain == leaks the digest one character at a time to anyone
    # who can measure the response
    if not hmac.compare_digest(expected, header[len("sha256=") :]):
        raise HTTPException(status_code=403, detail="invalid signature")


def check_verify_token(token: str | None) -> None:
    """The one-time GET handshake. Same unset rule as `check_signature`."""
    settings = get_settings()
    secret = (settings.META_VERIFY_TOKEN or "").strip()
    if not secret:
        if settings.is_prod:
            log.error("META_VERIFY_TOKEN unset in prod — refusing the handshake")
            raise HTTPException(
                status_code=503,
                detail="webhook not configured — set META_VERIFY_TOKEN",
            )
        return
    if not hmac.compare_digest(token or "", secret):
        raise HTTPException(status_code=403, detail="invalid verify token")


# ---- payload ------------------------------------------------------------------


def leadgen_values(payload: dict) -> list[dict]:
    """Every `entry[].changes[].value` whose field is `leadgen`.

    Meta batches: one POST can carry several entries and several changes per entry,
    and a Page subscribed to more than one field delivers those here too. A change
    with no `leadgen_id` is nothing we can act on, so it is dropped rather than
    recorded as a failure nobody can retry.
    """
    out: list[dict] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") != "leadgen":
                continue
            value = change.get("value") or {}
            if value.get("leadgen_id"):
                out.append(value)
    return out


def flatten(lead: dict) -> dict:
    """`field_data` -> {field name: first value}.

    Built-in fields and custom questions come back the same shape. Names are passed
    through untouched: `_norm_header` in leads_sync lowercases, strips the trailing
    '?' and applies the three aliases the Noida form needs.
    """
    row: dict[str, str] = {}
    for field in lead.get("field_data") or []:
        name = (field.get("name") or "").strip()
        if not name:
            continue
        values = field.get("values") or []
        row[name] = values[0] if values else ""
    return row


async def fetch_lead(leadgen_id: str) -> dict:
    """The lead behind a leadgen_id. Meta returns errors as real 4xx here (unlike
    Bonvoice), so `raise_for_status` is a truthful check."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{settings.meta_graph_base}/{leadgen_id}",
            params={"fields": LEAD_FIELDS, "access_token": settings.META_ACCESS_TOKEN},
        )
    resp.raise_for_status()
    return resp.json()


# ---- persistence --------------------------------------------------------------

# The subselect reads the PRE-statement snapshot, so it returns the status this row
# had before this delivery touched it — NULL when the row is new. A separate SELECT
# would race a second delivery of the same leadgen_id, which is exactly what Meta's
# retry produces.
UPSERT_EVENT = text("""
    INSERT INTO meta_lead_events (meta_lead_id, page_id, form_id, raw_webhook)
    VALUES (:lid, :page_id, :form_id, CAST(:raw_webhook AS jsonb))
    ON CONFLICT (meta_lead_id) DO UPDATE SET raw_webhook = EXCLUDED.raw_webhook
    RETURNING (SELECT e.status FROM meta_lead_events e
                WHERE e.meta_lead_id = :lid) AS prior_status
""")

MARK_EVENT = text("""
    UPDATE meta_lead_events
       SET status = :status,
           origin_key = :origin_key,
           attempts = attempts + 1,
           error_message = :error_message,
           processed_at = now(),
           campaign_id = :campaign_id,
           campaign_name = :campaign_name,
           adset_id = :adset_id,
           ad_id = :ad_id,
           ad_name = :ad_name,
           raw_lead = CAST(:raw_lead AS jsonb)
     WHERE meta_lead_id = :lid
""")

# Stamp the lead this delivery produced — or the one it was absorbed into, when the
# buyer already existed from the sheet or an earlier form. Guarded on IS NULL so a
# second delivery never rewrites the first attribution: `origin_key` is the lead's
# identity, and meta_lead_events keeps every delivery either way.
STAMP_LEAD = text("""
    UPDATE leads SET meta_lead_id = :lid
     WHERE origin_key = :origin_key AND meta_lead_id IS NULL
""")


async def _record(sql, params: dict) -> None:
    engine = neon_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL not configured")
    async with engine.begin() as conn:
        await conn.execute(sql, params)


async def process_value(value: dict, payload: dict) -> str:
    """One leadgen notification, end to end. Returns the terminal status.

    Never raises. A delivery that fails is a row this endpoint can show you and retry;
    a delivery that raises is a 500 Meta reads as "resend the whole batch", which
    re-runs the ones that already worked.
    """
    lid = str(value["leadgen_id"])
    engine = neon_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL not configured")

    async with engine.begin() as conn:
        prior = (await conn.execute(UPSERT_EVENT, {
            "lid": lid,
            "page_id": value.get("page_id"),
            "form_id": value.get("form_id"),
            "raw_webhook": json.dumps(payload),
        })).scalar()

    if prior == "success":
        # Meta retry of a delivery already in the CRM. Touching the lead again would
        # be the one thing idempotency exists to prevent.
        log.info("meta lead %s already processed — skipping", lid)
        return "duplicate"

    try:
        lead = await fetch_lead(lid)
        row = flatten(lead)
        phone = norm_phone(row.get("phone_number"))
        result = await ingest_meta_rows([row], actor="meta-webhook")
        origin_key = f"meta:{phone}" if phone else None
        if origin_key:
            await _record(STAMP_LEAD, {"lid": lid, "origin_key": origin_key})
            status, error = "success", None
        else:
            # `build_meta` skips a row with no phone, which is the right call — phone is
            # the lead's identity and a half-filled form row is normal. But the delivery
            # still produced no lead, and calling that `success` would put a green "in
            # CRM" chip on a lead that is only at Meta. That is precisely the gap this
            # log exists to show, so it lands with the rest of the not-in-CRM rows.
            status = "failed"
            error = "no phone number in the form — phone is the lead's identity"
        log.info("meta lead %s ingested (%s): %s", lid, status, result)
    except Exception as exc:  # noqa: BLE001 — recorded, then reported to the caller
        lead, origin_key, status = {}, None, "failed"
        error = f"{type(exc).__name__}: {exc}"
        log.exception("meta lead %s failed", lid)

    await _record(MARK_EVENT, {
        "lid": lid,
        "status": status,
        "origin_key": origin_key,
        "error_message": error,
        "campaign_id": lead.get("campaign_id"),
        "campaign_name": lead.get("campaign_name"),
        "adset_id": lead.get("adset_id"),
        "ad_id": lead.get("ad_id"),
        "ad_name": lead.get("ad_name"),
        "raw_lead": json.dumps(lead),
    })
    return status
