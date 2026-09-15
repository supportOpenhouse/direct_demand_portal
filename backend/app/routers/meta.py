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

from ..core.auth import current_user, require_admin
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
#
# The page, its count and its status counts share ONE filter clause, so they can never
# disagree about which deliveries a filter selects. A blank filter arrives as NULL and
# constrains nothing — `CAST(:x AS text)`, because asyncpg can't type a bare NULL.
UNASSIGNED = "__unassigned__"  # the "Unassigned" owner option: no RM, or no lead at all

_FROM = """
      FROM meta_lead_events e
      LEFT JOIN leads l ON l.origin_key = e.origin_key
"""
_WHERE = """
     WHERE (CAST(:status AS text) IS NULL OR e.status = CAST(:status AS text))
       AND (CAST(:campaign AS text) IS NULL OR e.campaign_name = CAST(:campaign AS text))
       AND (CAST(:adset AS text) IS NULL OR e.raw_lead->>'adset_name' = CAST(:adset AS text))
       AND (CAST(:ad AS text) IS NULL OR e.ad_name = CAST(:ad AS text))
       AND (CAST(:form AS text) IS NULL OR e.form_id = CAST(:form AS text))
       AND (CAST(:owner AS text) IS NULL
            OR (CAST(:owner AS text) = CAST(:unassigned AS text)
                AND coalesce(btrim(l.assigned_to), '') = '')
            OR l.assigned_to = CAST(:owner AS text))
"""
LIST_EVENTS = text(f"""
    SELECT e.meta_lead_id, e.status, e.attempts, e.error_message,
           e.received_at, e.processed_at,
           e.page_id, e.form_id, e.campaign_id, e.campaign_name,
           e.adset_id, e.ad_id, e.ad_name, e.raw_lead,
           l.id AS lead_id, l.name AS lead_name, l.phone AS lead_phone,
           l.stage AS lead_stage, l.city AS lead_city, l.assigned_to AS lead_assigned_to
{_FROM}{_WHERE}
     ORDER BY e.received_at DESC, e.meta_lead_id
     LIMIT :limit OFFSET :offset
""")
COUNT_EVENTS = text(f"SELECT count(*) {_FROM}{_WHERE}")
STATUS_COUNTS = text(f"SELECT e.status, count(*) AS n {_FROM}{_WHERE} GROUP BY e.status")
# Every value each filter can take, over the WHOLE table — not the loaded page, or a
# campaign further down the list could never be picked.
FACETS = text("""
    SELECT count(*) AS total_all,
           array_remove(array_agg(DISTINCT nullif(e.campaign_name, '')), NULL) AS campaigns,
           array_remove(array_agg(DISTINCT nullif(e.raw_lead->>'adset_name', '')), NULL) AS adsets,
           array_remove(array_agg(DISTINCT nullif(e.ad_name, '')), NULL) AS ads,
           array_remove(array_agg(DISTINCT nullif(e.form_id, '')), NULL) AS forms
      FROM meta_lead_events e
""")
OWNER_COUNTS = text(f"""
    SELECT CASE WHEN coalesce(btrim(l.assigned_to), '') = '' THEN NULL
                ELSE l.assigned_to END AS owner,
           count(*) AS n
{_FROM}
     GROUP BY 1
""")


def _responses(raw: dict) -> list[dict]:
    """`field_data` -> [{question, answer}], in the order the form asked them.

    A list, not a dict: `flatten` would collapse it and lose that order, and a form
    reads wrong out of order. The field NAMES are Meta's own and differ per form —
    nothing here may assume a fixed set.
    """
    return [
        {"question": (f.get("name") or "").strip(),
         "answer": (f.get("values") or [""])[0]}
        for f in (raw.get("field_data") or [])
        if (f.get("name") or "").strip()
    ]


LEAD_FORM = text("""
    SELECT e.meta_lead_id, e.received_at, e.raw_lead,
           e.campaign_name, e.ad_name
      FROM meta_lead_events e
      -- origin_key, NEVER leads.meta_lead_id: that column holds only the FIRST
      -- delivery's id (STAMP_LEAD is guarded IS NULL), so joining on it drops every
      -- repeat submission from the same buyer -- exactly the case where a second,
      -- different set of answers exists and is worth showing.
      -- A merged lead also owns every key folded into it (merged_origin_keys): without
      -- that, a buyer whose Meta arrival was merged into their MagicBricks/WhatsApp
      -- lead has a form nobody can see.
      JOIN leads l ON (l.origin_key = e.origin_key OR e.origin_key = ANY(l.merged_origin_keys))
      -- cast the uuid to text, not the param to uuid: entity ids reach us as strings
      -- and casting the other way raises on anything that isn't one
     WHERE l.id::text = :lead_id
     ORDER BY e.received_at DESC
     LIMIT 20
""")


@router.get("/lead/{lead_id}/form")
async def lead_form(lead_id: str, _: dict = Depends(current_user)):
    """The Instant Form answers behind one lead — for the lead popup.

    Deliberately NOT admin-gated, unlike the delivery log below: that is an
    account-wide record of what arrived, this is one lead's own source data and is
    visible to whoever can already open the lead. Same split as
    `/activity/entity/{type}/{id}`.

    Newest delivery first. A buyer who submitted twice has two, and the popup says so
    rather than silently rendering only one.
    """
    engine = neon_engine()
    if engine is None:
        return {"items": []}
    async with engine.connect() as conn:
        rows = (await conn.execute(LEAD_FORM, {"lead_id": lead_id})).mappings().all()
    return {"items": [{
        "meta_lead_id": r["meta_lead_id"],
        "received_at": r["received_at"].isoformat() if r["received_at"] else None,
        # Which ad produced this lead. Nullable on purpose: a lead from the Lead Ads
        # Testing Tool carries no campaign at all, and inventing a label for one would
        # claim an attribution that does not exist.
        "campaign_name": r["campaign_name"],
        "ad_name": r["ad_name"],
        "responses": _responses(r["raw_lead"] or {}),
    } for r in rows]}


PAGE_SIZE = 100


def _filters(status, campaign, adset, ad, form, owner) -> dict:
    """Query-string filters → SQL params. Blank is NULL (no constraint); values are
    otherwise passed exactly, since they match stored values exactly."""
    def clean(v):
        return v if v and v.strip() else None
    return {"status": clean(status), "campaign": clean(campaign), "adset": clean(adset),
            "ad": clean(ad), "form": clean(form), "owner": clean(owner),
            "unassigned": UNASSIGNED}


@router.get("/leads")
async def list_meta_leads(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=500),
    status: str | None = None,
    campaign: str | None = None,
    adset: str | None = None,
    ad: str | None = None,
    form: str | None = None,
    owner: str | None = None,
    _: dict = Depends(require_admin),
):
    """Every webhook delivery and what became of it, a page at a time. Admin only.

    Filtering and counting happen HERE, over every delivery — not in the browser over
    the rows it has loaded, which once the list is paged would make every count and
    every filter silently describe only what has been scrolled into view.

    `total` = deliveries matching every filter · `status_counts` = the same minus the
    status filter (the status buttons) · `facets` = every value each filter can take.
    """
    engine = neon_engine()
    if engine is None:
        return {"status": "not_configured", "total": 0, "total_all": 0, "status_counts": {},
                "facets": {"campaigns": [], "adsets": [], "ads": [], "forms": [],
                           "owners": {}, "unassigned": 0},
                "items": [], "next_offset": None}

    p = _filters(status, campaign, adset, ad, form, owner)
    async with engine.connect() as conn:
        rows = (await conn.execute(
            LIST_EVENTS, {**p, "limit": limit, "offset": offset})).mappings().all()
        total = (await conn.execute(COUNT_EVENTS, p)).scalar() or 0
        status_counts = {r["status"]: r["n"] for r in (await conn.execute(
            STATUS_COUNTS, {**p, "status": None})).mappings()}
        facet = (await conn.execute(FACETS)).mappings().first()
        owner_rows = (await conn.execute(OWNER_COUNTS)).mappings().all()

    items = []
    for r in rows:
        raw = r["raw_lead"] or {}
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
            "responses": _responses(raw),
            "lead": {
                "id": str(r["lead_id"]),
                "name": r["lead_name"],
                "phone": r["lead_phone"],
                "stage": r["lead_stage"],
                "city": r["lead_city"],
                "assigned_to": r["lead_assigned_to"],
            } if r["lead_id"] else None,
        })
    return {
        "status": "ok",
        "total": total,
        "total_all": facet["total_all"],
        "status_counts": status_counts,
        "facets": {
            "campaigns": sorted(facet["campaigns"] or [], key=str.lower),
            "adsets": sorted(facet["adsets"] or [], key=str.lower),
            "ads": sorted(facet["ads"] or [], key=str.lower),
            "forms": sorted(facet["forms"] or []),
            "owners": {r["owner"]: r["n"] for r in owner_rows if r["owner"]},
            "unassigned": sum(r["n"] for r in owner_rows if not r["owner"]),
        },
        "items": items,
        "next_offset": offset + len(items) if offset + len(items) < total else None,
    }
