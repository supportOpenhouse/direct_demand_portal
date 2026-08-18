"""Huvo Call Log — the page over huvo_call_updates, plus creating a lead from a call.

Deliberately not a copy of the Bonvoice call log's filters. That page describes a
telephony leg (who dialled, did it connect, how long); this one describes what was
said (the outcome, whether they're interested, what they scored). So "placed by" is
gone — Huvo reports no actor beyond bot/human — and "connected" is gone because
call_outcome answers it with sixteen values instead of two.

What's here instead: outcome, interest, and whether the call is attached to a lead at
all. That last one matters most — a third of the rows have no lead, and that set is
exactly the create-lead worklist.
"""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..core.auth import current_user, require_admin
from ..db import neon_engine
from ..models import Lead

log = logging.getLogger("huvo_calls")
router = APIRouter(tags=["huvo"])

# Sentinels for the "lead" dropdown. Not booleans in the querystring because a third
# state — no filter at all — has to be expressible too.
LINKED_YES = "linked"
LINKED_NO = "unlinked"

# Campaign names are free text from Huvo, so "" can't mean "no campaign" — it's
# indistinguishable from "no filter". This sentinel can't collide with a real name.
NO_CAMPAIGN = "__none__"

# Same labels and boundaries as the Bonvoice log's buckets. A bucket that meant
# something different on this page than that one would be a quiet trap.
DURATION_BUCKETS: dict[str, tuple[int, int | None]] = {
    "<1 min": (0, 60),
    "1-3 mins": (60, 180),
    "3-5 mins": (180, 300),
    "5+ mins": (300, None),
}

_FROM = " FROM huvo_call_updates h LEFT JOIN leads l ON l.id = h.lead_id"


def calls_filters(q, outcome, interested, linked, duration, campaign=None) -> tuple[str, dict]:
    """WHERE clause + bound params. Every value is bound; the search box is free text
    from a browser and this reaches SQL."""
    where, params = [], {}

    if q and q.strip():
        # summary is included because it's the only place the conversation itself is
        # recorded — searching it is how you find "the one about the Whitefield 2BHK"
        where.append("(h.from_number ILIKE :q OR h.caller_name ILIKE :q "
                     "OR h.summary ILIKE :q OR l.name ILIKE :q "
                     "OR h.campaign_name ILIKE :q)")
        params["q"] = f"%{q.strip()}%"

    if outcome:
        where.append("h.call_outcome = :outcome")
        params["outcome"] = outcome

    if interested:
        where.append("h.is_interested = :interested")
        params["interested"] = interested

    # An unrecognised value is ignored rather than matched: a stale querystring
    # shouldn't silently render an empty page.
    if linked == LINKED_YES:
        where.append("h.lead_id IS NOT NULL")
    elif linked == LINKED_NO:
        where.append("h.lead_id IS NULL")

    # Equality, not LIKE: two campaigns sharing a prefix would otherwise fold into one.
    if campaign == NO_CAMPAIGN:
        where.append("h.campaign_name IS NULL")
    elif campaign:
        where.append("h.campaign_name = :campaign")
        params["campaign"] = campaign

    if duration in DURATION_BUCKETS:
        lo, hi = DURATION_BUCKETS[duration]
        where.append("h.duration_sec >= :dur_lo")
        params["dur_lo"] = lo
        if hi is not None:
            where.append("h.duration_sec < :dur_hi")
            params["dur_hi"] = hi

    return (" WHERE " + " AND ".join(where)) if where else "", params


@router.get("/huvo/calls", dependencies=[Depends(require_admin)])
async def huvo_calls(
    q: str | None = Query(None),
    outcome: str | None = Query(None),
    interested: str | None = Query(None),
    linked: str | None = Query(None),
    duration: str | None = Query(None),
    campaign: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Every Huvo call, newest first."""
    engine = neon_engine()
    if engine is None:
        return {"items": [], "total": 0}
    clause, params = calls_filters(q, outcome, interested, linked, duration, campaign)
    async with engine.connect() as conn:
        # Both counts in one round trip. unique_leads is distinct numbers, not rows:
        # Huvo calls the same person more than once, so "1415 calls" alone overstates
        # how many people are actually in the list.
        # All three counts in one round trip. unlinked_unique is what the bulk-create
        # button offers: distinct numbers matching the CURRENT FILTERS that have no
        # lead — not what happens to be on this page, which is a different and much
        # smaller number.
        counts = (await conn.execute(text(
            f"SELECT count(*) AS total,"
            f"       count(DISTINCT h.from_number) AS uniq,"
            f"       count(DISTINCT h.from_number) FILTER (WHERE h.lead_id IS NULL) AS unlinked"
            f"{_FROM}{clause}"), params)).mappings().first()
        total, unique_leads = counts["total"], counts["uniq"]
        unlinked_unique = counts["unlinked"]
        rows = (await conn.execute(text(f"""
            SELECT h.id, h.campaign_name, h.from_number, h.caller_name, h.call_outcome, h.is_interested,
                   h.rsvp_status, h.lead_score, h.budget_lacs, h.summary,
                   h.recording_url, h.duration_sec, h.started_at, h.received_at,
                   h.lead_id, l.name AS lead_name, l.stage AS lead_stage
            {_FROM}{clause}
             -- started_at is null for the rows that record no call, so they'd sort
             -- last forever; received_at keeps them in the timeline
             ORDER BY COALESCE(h.started_at, h.received_at) DESC
             LIMIT :limit OFFSET :offset"""),
            {**params, "limit": limit, "offset": offset})).mappings().all()
    return {"items": [
        {k: (v.isoformat() if isinstance(v, datetime)
             else str(v) if isinstance(v, UUID)
             else float(v) if hasattr(v, "quantize")  # Numeric -> JSON number
             else v)
         for k, v in dict(r).items()}
        for r in rows
    ], "total": total, "unique_leads": unique_leads,
        "unlinked_unique": unlinked_unique}


@router.get("/huvo/calls/outcomes", dependencies=[Depends(require_admin)])
async def huvo_call_outcomes():
    """Outcomes actually present, for the dropdown.

    Derived rather than hardcoded from their enum: the page holds 50 rows at a time, so
    building the list from what's on screen would hide most of it, and a value Huvo
    adds later shows up here without a deploy.
    """
    engine = neon_engine()
    if engine is None:
        return {"outcomes": [], "interest": [], "campaigns": []}
    async with engine.connect() as conn:
        outcomes = (await conn.execute(text(
            "SELECT DISTINCT call_outcome FROM huvo_call_updates "
            "WHERE call_outcome IS NOT NULL ORDER BY 1"))).scalars().all()
        interest = (await conn.execute(text(
            "SELECT DISTINCT is_interested FROM huvo_call_updates "
            "WHERE is_interested IS NOT NULL ORDER BY 1"))).scalars().all()
        campaigns = (await conn.execute(text(
            "SELECT DISTINCT campaign_name FROM huvo_call_updates "
            "WHERE campaign_name IS NOT NULL ORDER BY 1"))).scalars().all()
    return {"outcomes": list(outcomes), "interest": list(interest),
            "campaigns": list(campaigns)}


@router.get("/leads/{lead_id}/huvo-calls")
async def lead_huvo_calls(lead_id: UUID, _: dict = Depends(current_user)):
    """Huvo's calls to one lead, newest first — the lead-detail card.

    current_user, not admin: an RM looking at their own lead needs to see what the bot
    already asked it. The Huvo Call Log page stays admin-only because that one is
    every lead at once.

    Includes payload so the card can show what the caller actually said — the fields
    that matter most here (what they want, why they're interested) have no column.
    """
    engine = neon_engine()
    if engine is None:
        return {"items": []}
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT id, campaign_name, call_outcome, is_interested, rsvp_status, lead_score,
                   budget_lacs, summary, recording_url, duration_sec,
                   started_at, received_at, payload
              FROM huvo_call_updates
             WHERE lead_id = :id
             ORDER BY COALESCE(started_at, received_at) DESC
             LIMIT 50"""), {"id": lead_id})).mappings().all()
    return {"items": [
        {k: (v.isoformat() if isinstance(v, datetime)
             else str(v) if isinstance(v, UUID)
             else float(v) if hasattr(v, "quantize")
             else v)
         for k, v in dict(r).items()}
        for r in rows
    ]}


# Registered AFTER /huvo/calls/outcomes on purpose: FastAPI matches in declaration
# order, and a bare {call_id} here would swallow "outcomes" and 422 on it.
@router.get("/huvo/calls/{call_id}", dependencies=[Depends(require_admin)])
async def huvo_call_detail(call_id: UUID):
    """One call, with the whole envelope.

    `payload` is excluded from the list query because it's the largest column by far
    and nothing in a table renders it — but it's the only place nine of Huvo's
    analytics fields live (project_name, interest_reason, purpose, location,
    type_of_property, the two schedule fields, follow_up_time, callback_owner), so
    the detail view has to have it.
    """
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    async with engine.connect() as conn:
        row = (await conn.execute(text(f"""
            SELECT h.*, l.name AS lead_name, l.stage AS lead_stage
            {_FROM} WHERE h.id = :id"""), {"id": call_id})).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="call not found")
    return {k: (v.isoformat() if isinstance(v, datetime)
                else str(v) if isinstance(v, UUID)
                else float(v) if hasattr(v, "quantize")
                else v)
            for k, v in dict(row).items()}


class HuvoLeadRequest(BaseModel):
    phone: str
    name: str = Field(min_length=1, max_length=120)
    city: str | None = None
    society: str | None = None


@router.post("/huvo/leads")
async def huvo_create_lead(req: HuvoLeadRequest, user: dict = Depends(current_user)):
    """Create a lead from a Huvo call.

    Mirrors the WhatsApp flow (routers/gupshup.py) — idempotent on origin_key, so a
    double-click returns the existing lead rather than a duplicate.

    Then back-links every Huvo call from that number. The webhook resolves lead_id at
    write time only, so without this the calls that prompted the lead would stay
    orphaned from it — which is precisely backwards.
    """
    from ..services.leads_sync import TAT_HOURS, display_phone, norm_phone

    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    phone10 = norm_phone(req.phone)
    if not phone10 or len(phone10) != 10:
        raise HTTPException(status_code=400, detail="invalid phone number")

    now = datetime.now(timezone.utc)
    values = {
        "origin_key": f"huvo:{phone10}", "source_category": "huvo", "source": "huvo",
        "name": req.name.strip(), "phone": display_phone(phone10),
        "city": (req.city or "").strip() or None,
        "society": (req.society or "").strip() or None,
        "received_at": now, "tat_deadline": now + timedelta(hours=TAT_HOURS),
        "source_meta": {"created_from": "huvo_call_log", "created_by": user.get("email")},
    }
    async with engine.begin() as conn:
        await conn.execute(
            pg_insert(Lead).values(values).on_conflict_do_nothing(index_elements=["origin_key"])
        )
        # Not by origin_key: the number may already exist as a lead from another source
        # (a portal, WhatsApp), in which case the insert above did nothing and THAT
        # lead is the one these calls belong to.
        lead_id = (await conn.execute(text(
            "SELECT id FROM leads WHERE phone IS NOT NULL "
            " AND right(regexp_replace(phone, '[^0-9]', '', 'g'), 10) = :p "
            " ORDER BY (stage IN ('won','rejected','rnr')), created_at DESC LIMIT 1"),
            {"p": phone10})).scalar()
        linked = (await conn.execute(text(
            "UPDATE huvo_call_updates SET lead_id = :lead "
            " WHERE from_number = :p AND lead_id IS NULL"),
            {"lead": lead_id, "p": phone10})).rowcount

    log.info("huvo: lead %s from call log by %s (%d calls linked)",
             lead_id, user.get("email"), linked)
    return {"status": "ok", "lead_id": str(lead_id) if lead_id else None, "calls_linked": linked}


class BulkHuvoLeadRequest(BaseModel):
    """Either an explicit selection, or every unlinked call matching a filter.

    Both modes exist because they answer different questions. Ticking boxes is right
    for "these five"; but "all 845 unlinked" can't be expressed as a phone list the
    browser sends — it would have to page through the whole table first, and the list
    would be stale by the time it arrived. So for that, the filter travels instead and
    the server resolves the set itself.
    """
    # capped so one click can't fan out into an unbounded write
    phones: list[str] | None = Field(default=None, max_length=500)

    # ...or resolve the set server-side from the same filters the page is showing.
    # `linked` is deliberately not accepted: this only ever creates leads for calls
    # that have none, whatever the page's Lead filter happens to be set to.
    all_matching: bool = False
    q: str | None = None
    outcome: str | None = None
    interested: str | None = None
    duration: str | None = None
    campaign: str | None = None


@router.post("/huvo/leads/bulk")
async def huvo_bulk_create_leads(req: BulkHuvoLeadRequest, user: dict = Depends(current_user)):
    """Create leads from many Huvo calls at once.

    Names come from the stored calls, not from the client's list — a stale browser
    can't stamp the wrong name on a lead. Leads are created UNASSIGNED, matching the
    WhatsApp bulk flow: ownership stays a separate decision made through assign.

    Idempotent on origin_key, so a number that already has a lead is counted as
    skipped rather than duplicated — and its calls are still back-linked, which is the
    whole point of running this over a filtered "No lead yet" list.
    """
    from ..services.leads_sync import TAT_HOURS, display_phone, norm_phone

    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")

    now = datetime.now(timezone.utc)
    async with engine.begin() as conn:
        if req.all_matching:
            # Resolved here, not in the browser: the same filters the page is showing,
            # forced to the unlinked subset.
            clause, params = calls_filters(
                req.q, req.outcome, req.interested, LINKED_NO, req.duration, req.campaign)
            phones10 = list((await conn.execute(text(
                f"SELECT DISTINCT h.from_number{_FROM}{clause}"
                f"{' AND' if clause else ' WHERE'} h.from_number IS NOT NULL"),
                params)).scalars().all())
        else:
            # dedupe: the same person can appear on several calls in the selection
            phones10 = sorted({p10 for p10 in (norm_phone(p) for p in (req.phones or []))
                               if p10 and len(p10) == 10})
        if not phones10:
            raise HTTPException(status_code=400, detail="no calls to convert")

        # Best known name per number: the most recent call that actually carried one.
        # "Customer" is Huvo's placeholder for a caller it never identified — taking it
        # would name a lead "Customer" when an earlier call knew better.
        names = {r["from_number"]: r["caller_name"] for r in (await conn.execute(text("""
            SELECT DISTINCT ON (from_number) from_number, caller_name
              FROM huvo_call_updates
             WHERE from_number = ANY(:ps) AND caller_name IS NOT NULL
             ORDER BY from_number, (caller_name = 'Customer'), received_at DESC"""),
            {"ps": phones10})).mappings().all()}

        values = [{
            "origin_key": f"huvo:{p}", "source_category": "huvo", "source": "huvo",
            "name": names.get(p) or "Unknown caller", "phone": display_phone(p),
            "received_at": now, "tat_deadline": now + timedelta(hours=TAT_HOURS),
            "source_meta": {"created_from": "huvo_call_log_bulk",
                            "created_by": user.get("email")},
        } for p in phones10]
        await conn.execute(
            pg_insert(Lead).values(values).on_conflict_do_nothing(index_elements=["origin_key"])
        )

        # Link by phone, not origin_key: a number may already be a lead from a portal
        # or WhatsApp, and THAT lead is the one these calls belong to.
        linked = (await conn.execute(text("""
            UPDATE huvo_call_updates h
               SET lead_id = l.id
              FROM (SELECT DISTINCT ON (right(regexp_replace(phone,'[^0-9]','','g'),10))
                           right(regexp_replace(phone,'[^0-9]','','g'),10) AS p10, id
                      FROM leads WHERE phone IS NOT NULL
                     ORDER BY p10, (stage IN ('won','rejected','rnr')), created_at DESC) l
             WHERE h.from_number = l.p10
               AND h.from_number = ANY(:ps)
               AND h.lead_id IS NULL"""), {"ps": phones10})).rowcount

        created = (await conn.execute(text(
            "SELECT count(*) FROM leads WHERE origin_key = ANY(:ks) "
            "  AND source_meta->>'created_from' = 'huvo_call_log_bulk'"),
            {"ks": [f"huvo:{p}" for p in phones10]})).scalar()

    log.info("huvo: bulk %d numbers by %s — %d calls linked",
             len(phones10), user.get("email"), linked)
    return {"status": "ok", "requested": len(phones10),
            "created": created, "calls_linked": linked}
