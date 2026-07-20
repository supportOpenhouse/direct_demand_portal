from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..core.auth import assignment_aliases, current_user
from ..db import neon_engine
from ..models import LeadConfirmedData, LeadNote, Visit
from ..services.leads_sync import read_leads_state, run_leads_sync
from ..services.matching import match_lead, match_preview
from ..services.societies import (
    localities_in_micromarket,
    search_localities,
    search_micromarkets,
    search_societies,
    societies_in_locality,
)

router = APIRouter(tags=["leads"], dependencies=[Depends(current_user)])

# stages that take a lead out of the active funnel (rnr = Ring No Response, terminal)
_TERMINAL = "('won','lost','rejected','future_prospect','timepass','rnr')"

# a lead is "in Pipeline" once a visit has been booked for it on the Openhouse app
_HAS_VISIT = "SELECT 1 FROM crm_visits v WHERE v.lead_id = leads.id"

# segment → SQL predicate on the leads spine.
#   new       — untouched: no call logged yet (no open follow-up)
#   followup  — any non-terminal lead with an open follow-up. Pre-qualification leads
#               (not-connected + saved-not-qualified) live ONLY here; qualified+ leads
#               also appear in their stage tab, here as a due-callback reminder.
#   rnr       — never-connected leads escalated after 10 consecutive missed calls
SEGMENTS = {
    "new": "stage = 'new' AND follow_up_at IS NULL",
    "followup": f"stage NOT IN {_TERMINAL} AND follow_up_at IS NOT NULL",
    # Qualified = confirmed on call, or a trip planned locally (preparation) — but no visit
    # booked yet. Booking a real visit moves the lead to Pipeline.
    "qualified": f"stage NOT IN {_TERMINAL} AND stage <> 'visit_scheduled' "
                 f"AND NOT EXISTS ({_HAS_VISIT}) "
                 "AND (confirmed = true OR stage = 'visit_planned')",
    # Pipeline = a visit is actually booked on the Openhouse app. PLUS a safety net: a lead
    # worked past New that matches no other tab would vanish entirely — catch it here.
    "pipeline": f"stage NOT IN {_TERMINAL} AND ("
                f"EXISTS ({_HAS_VISIT}) OR stage = 'visit_scheduled' "
                "OR (stage NOT IN ('new','visit_planned') AND confirmed = false "
                "AND qualified_at IS NULL AND follow_up_at IS NULL))",
    "converted": "stage = 'won'",
    "rnr": "stage = 'rnr'",
    "rejected": "stage = 'rejected'",
}


def _parse_followup(raw: str | None) -> datetime:
    """Parse a required ISO-8601 UTC follow-up time (frontend sends `…Z`)."""
    if not raw:
        raise HTTPException(status_code=422, detail={"fields": ["follow_up_at"], "message": "follow-up is required"})
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail={"fields": ["follow_up_at"]})


def _lead_row(r) -> dict:
    # source remarks (seeded, " | "-joined) + manual lead_notes form the thread; the
    # list query supplies the newest manual note + its count (None on other queries).
    remarks = [p.strip() for p in (r["source_remarks"] or "").split(" | ") if p.strip()]
    return {
        "id": str(r["id"]),
        "source_category": r["source_category"],
        "source": r["source"],
        "name": r["name"],
        "phone": r["phone"],
        "email": r["email"],
        "assigned_to": r["assigned_to"],
        "city": r["city"],
        "society": r["society"],
        "configuration": r["configuration"],
        "budget_band": r["budget_band"],
        "plan_to_buy": r["plan_to_buy"],
        "preferred_visit_day": r["preferred_visit_day"],
        "source_remarks": r["source_remarks"],
        "source_meta": r["source_meta"],
        "received_at": r["received_at"].isoformat() if r["received_at"] else None,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "stage": r["stage"],
        "tat_deadline": r["tat_deadline"].isoformat() if r["tat_deadline"] else None,
        "reject_reason": r["reject_reason"],
        "reject_notes": r["reject_notes"],
        "rejected_at": r["rejected_at"].isoformat() if r["rejected_at"] else None,
        "confirmed": r["confirmed"],
        "qualified_at": r["qualified_at"].isoformat() if r["qualified_at"] else None,
        "follow_up_since": r["follow_up_since"].isoformat() if r["follow_up_since"] else None,
        "follow_up_at": r["follow_up_at"].isoformat() if r["follow_up_at"] else None,
        "miss_count": r["miss_count"] or 0,
        "ever_connected": r["ever_connected"],
        "is_hot": bool(r["is_hot"]),
        # latest booked visit (Pipeline status chip) — only present on the list query
        "visit_status": r.get("visit_status"),
        "visit_date": r.get("visit_sel_date"),
        "visit_count": int(r.get("visit_count") or 0),
        "latest_note": r.get("latest_note_body") or (remarks[-1] if remarks else None),
        "latest_note_at": r["latest_note_at"].isoformat() if r.get("latest_note_at") else None,
        "note_count": int(r.get("note_count") or 0) + len(remarks),
        "is_test": r["is_test"],
    }


@router.get("/leads")
async def list_leads(segment: str = Query("new"), user: dict = Depends(current_user)):
    engine = neon_engine()
    if engine is None:
        return {"status": "not_configured", "detail": "Set DATABASE_URL", "items": [], "sync": None}
    predicate = SEGMENTS.get(segment)
    if predicate is None:
        raise HTTPException(status_code=400, detail=f"unknown segment '{segment}'")
    # role-scoping: unassigned leads are visible to admins only. RM → own assigned
    # leads only; CM → all assigned leads (no unassigned); Admin → everything.
    params: dict = {}
    role = user.get("role")
    if role == "cm":
        predicate += " AND assigned_to IS NOT NULL"
    elif role == "rm":
        aliases = assignment_aliases(user)
        if aliases:
            predicate += " AND lower(assigned_to) = ANY(:aliases)"
            params["aliases"] = aliases
        else:
            predicate += " AND false"
    # Follow-up is a worklist — soonest/overdue callbacks first; others newest-first.
    order = "follow_up_at ASC NULLS LAST" if segment == "followup" else "created_at DESC"
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text(
                    "SELECT leads.*, "
                    "(SELECT body FROM lead_notes WHERE lead_id = leads.id ORDER BY created_at DESC LIMIT 1) AS latest_note_body, "
                    "(SELECT created_at FROM lead_notes WHERE lead_id = leads.id ORDER BY created_at DESC LIMIT 1) AS latest_note_at, "
                    "(SELECT count(*) FROM lead_notes WHERE lead_id = leads.id) AS note_count, "
                    "(SELECT status FROM crm_visits WHERE lead_id = leads.id ORDER BY created_at DESC LIMIT 1) AS visit_status, "
                    "(SELECT selected_date FROM crm_visits WHERE lead_id = leads.id ORDER BY created_at DESC LIMIT 1) AS visit_sel_date, "
                    "(SELECT count(*) FROM crm_visits WHERE lead_id = leads.id) AS visit_count "
                    f"FROM leads WHERE {predicate} ORDER BY is_test DESC, {order}"
                ),
                params,
            )
            items = [_lead_row(m) for m in res.mappings()]
    except Exception as e:  # table missing / conn error
        return {"status": "error", "detail": str(e), "items": [], "sync": None}
    return {"status": "ok", "detail": None, "items": items, "sync": await read_leads_state()}


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: UUID):
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT * FROM leads WHERE id = :id"), {"id": lead_id})
        row = res.mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="lead not found")
        lead = _lead_row(row)
        cres = await conn.execute(
            text("SELECT * FROM lead_confirmed_data WHERE lead_id = :id"), {"id": lead_id}
        )
        c = cres.mappings().first()
    def _num(v):
        return float(v) if v is not None else None
    lead["confirmed_data"] = (
        {
            "purpose": c["purpose"],
            "budget_min_lacs": _num(c["budget_min_lacs"]),
            "budget_max_lacs": _num(c["budget_max_lacs"]),
            "configuration": c["configuration"],
            "size_min_sqft": _num(c["size_min_sqft"]),
            "size_max_sqft": _num(c["size_max_sqft"]),
            "preferred_micromarkets": c["preferred_micromarkets"],
            "shortlisted_societies": c["shortlisted_societies"],
            "preferred_localities": c["preferred_localities"],
            "office_willing": c["office_willing"],
            "office_preferred_date": c["office_preferred_date"].isoformat() if c["office_preferred_date"] else None,
            "remark": c["remark"],
            "confirmed_at": c["confirmed_at"].isoformat() if c["confirmed_at"] else None,
        }
        if c
        else None
    )
    return lead


@router.get("/leads/{lead_id}/matches")
async def lead_matches(lead_id: UUID):
    """Top-5 live inventory + top-5 supply units matched to this lead."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT * FROM leads WHERE id = :id"), {"id": lead_id})
        row = res.mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="lead not found")
        cres = await conn.execute(
            text("SELECT * FROM lead_confirmed_data WHERE lead_id = :id"), {"id": lead_id}
        )
        c = cres.mappings().first()
    confirmed = dict(c) if c else None
    return await match_lead(dict(row), confirmed)


class MatchPreview(BaseModel):
    city: str | None = None
    societies: list[str] = []
    localities: list[str] = []
    micromarkets: list[str] = []
    configuration: str | None = None
    size_min_sqft: float | None = None
    size_max_sqft: float | None = None
    budget_min_lacs: float | None = None
    budget_max_lacs: float | None = None
    budget_band: str | None = None


@router.post("/leads/match-preview")
async def leads_match_preview(payload: MatchPreview):
    """Live matching for in-progress form fields — units are cached, so this is fast."""
    return await match_preview(payload.model_dump())


class ConfirmPayload(BaseModel):
    purpose: str
    budget_min_lacs: float
    budget_max_lacs: float
    configuration: str
    size_min_sqft: float | None = None
    size_max_sqft: float | None = None
    preferred_micromarkets: list[str] = []
    shortlisted_societies: list[str] = []
    preferred_localities: list[str] = []
    office_willing: str
    office_preferred_date: str | None = None
    remark: str | None = None
    follow_up_at: str             # mandatory — a follow-up is required to confirm/save
    qualify: bool = True          # True → qualify the lead; False → just save details + follow-up


@router.post("/leads/{lead_id}/confirm")
async def confirm_lead(lead_id: UUID, payload: ConfirmPayload):
    """Save the confirmed-on-call form + a mandatory follow-up. `qualify=true` moves the
    lead to Qualified (new → contacted); `qualify=false` just saves the details and keeps
    the lead in Follow-up (not qualified)."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    # mandatory: purpose, budget range, config, office-willing
    missing = [
        f for f, v in [("purpose", payload.purpose), ("budget_min_lacs", payload.budget_min_lacs),
                       ("budget_max_lacs", payload.budget_max_lacs),
                       ("configuration", payload.configuration), ("office_willing", payload.office_willing)]
        if v in (None, "", 0)
    ]
    if missing:
        raise HTTPException(status_code=422, detail={"fields": missing})
    if payload.budget_min_lacs > payload.budget_max_lacs:
        raise HTTPException(status_code=422, detail={"fields": ["budget_max_lacs"], "message": "max must be ≥ min"})
    follow_up = _parse_followup(payload.follow_up_at)
    office_date: date | None = None
    if payload.office_preferred_date:
        try:
            office_date = date.fromisoformat(payload.office_preferred_date)
        except ValueError:
            raise HTTPException(status_code=422, detail={"fields": ["office_preferred_date"]})
    from ..services.normalize import normalize_config
    values = dict(
        lead_id=lead_id, purpose=payload.purpose, budget_value_lacs=None, size_sqft=None,
        budget_min_lacs=payload.budget_min_lacs, budget_max_lacs=payload.budget_max_lacs,
        configuration=normalize_config(payload.configuration),
        size_min_sqft=payload.size_min_sqft, size_max_sqft=payload.size_max_sqft,
        preferred_micromarkets=payload.preferred_micromarkets,
        shortlisted_societies=payload.shortlisted_societies, preferred_localities=payload.preferred_localities,
        office_willing=payload.office_willing, office_preferred_date=office_date, remark=payload.remark,
    )
    async with engine.begin() as conn:
        exists = await conn.execute(text("SELECT stage FROM leads WHERE id = :id"), {"id": lead_id})
        if exists.first() is None:
            raise HTTPException(status_code=404, detail="lead not found")
        stmt = pg_insert(LeadConfirmedData).values(**values).on_conflict_do_update(
            index_elements=[LeadConfirmedData.lead_id],
            set_={k: v for k, v in values.items() if k != "lead_id"},
        )
        await conn.execute(stmt)
        # reaching this form means the call connected → never RNR. Always set the follow-up.
        if payload.qualify:
            # qualify: new → contacted, start the 7-day clock (only on first confirm)
            await conn.execute(
                text(
                    "UPDATE leads SET confirmed = true, ever_connected = true, miss_count = 0, "
                    "stage = CASE WHEN stage = 'new' THEN 'contacted' ELSE stage END, "
                    "tat_deadline = NULL, follow_up_at = :t, "
                    "follow_up_since = COALESCE(follow_up_since, now()), "
                    "qualified_at = COALESCE(qualified_at, now()) WHERE id = :id"
                ),
                {"id": lead_id, "t": follow_up},
            )
        else:
            # save details only — stays in Follow-up, not qualified
            await conn.execute(
                text("UPDATE leads SET ever_connected = true, miss_count = 0, follow_up_at = :t, "
                     "follow_up_since = COALESCE(follow_up_since, now()) WHERE id = :id"),
                {"id": lead_id, "t": follow_up},
            )
    return {"status": "ok"}


# --- call worklist (New Leads / Follow-up) -----------------------------------

class CallResult(BaseModel):
    connected: bool


@router.post("/leads/{lead_id}/call-result")
async def call_result(lead_id: UUID, payload: CallResult):
    """Log a call attempt from the New Leads / Follow-up worklist.
    connected=True  → opens the lead (caller navigates); resets the miss streak.
    connected=False → +3h follow-up; 10 consecutive misses on a never-connected lead → RNR."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT miss_count, ever_connected FROM leads WHERE id = :id"), {"id": lead_id}
        )).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="lead not found")
        if payload.connected:
            await conn.execute(
                text("UPDATE leads SET ever_connected = true, miss_count = 0 WHERE id = :id"), {"id": lead_id})
            return {"status": "ok", "connected": True, "moved_to_rnr": False}
        new_miss = (row["miss_count"] or 0) + 1
        to_rnr = (not row["ever_connected"]) and new_miss >= 10
        if to_rnr:
            await conn.execute(text(
                "UPDATE leads SET miss_count = :m, stage = 'rnr', follow_up_at = NULL, "
                "follow_up_since = NULL WHERE id = :id"),
                {"m": new_miss, "id": lead_id})
        else:
            await conn.execute(text(
                "UPDATE leads SET miss_count = :m, follow_up_at = now() + interval '3 hours', "
                "follow_up_since = COALESCE(follow_up_since, now()) WHERE id = :id"),
                {"m": new_miss, "id": lead_id})
        return {"status": "ok", "connected": False, "moved_to_rnr": to_rnr, "miss_count": new_miss}


class FollowupPayload(BaseModel):
    follow_up_at: str


@router.post("/leads/{lead_id}/followup")
async def set_followup(lead_id: UUID, payload: FollowupPayload):
    """Set a manual follow-up (reachable only after a connected call) → moves to Follow-up."""
    follow_up = _parse_followup(payload.follow_up_at)
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        res = await conn.execute(
            text("UPDATE leads SET follow_up_at = :t, ever_connected = true, miss_count = 0, "
                 "follow_up_since = COALESCE(follow_up_since, now()) WHERE id = :id"),
            {"t": follow_up, "id": lead_id})
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
    return {"status": "ok"}


@router.get("/leads/{lead_id}/crm-visits")
async def lead_crm_visits(lead_id: UUID):
    """Every visit booked on the Openhouse app for this lead — each has its own visit id
    and is a separate visit (a buyer often tours several societies)."""
    engine = neon_engine()
    if engine is None:
        return {"items": []}
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT visit_id, home_id, society, city, selected_date, selected_time, status, "
            "visit_date, buyer_feedback, sales_feedback, booked_by FROM crm_visits "
            "WHERE lead_id = :id ORDER BY selected_date DESC NULLS LAST, visit_id DESC"
        ), {"id": lead_id})).mappings().all()
    return {"items": [dict(r) for r in rows]}


class HotPayload(BaseModel):
    hot: bool


@router.post("/leads/{lead_id}/hot")
async def mark_hot(lead_id: UUID, payload: HotPayload):
    """Star / un-star a lead as hot (used by the Pipeline tab's filter)."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        res = await conn.execute(
            text("UPDATE leads SET is_hot = :h WHERE id = :id"), {"h": payload.hot, "id": lead_id})
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
    return {"status": "ok", "is_hot": payload.hot}


REJECT_REASONS = {"Broker", "Budget", "Location", "Requirement Mismatch", "No Requirement"}


class RejectPayload(BaseModel):
    reason: str
    notes: str


@router.post("/leads/{lead_id}/reject")
async def reject_lead(lead_id: UUID, payload: RejectPayload):
    if payload.reason not in REJECT_REASONS:
        raise HTTPException(status_code=422, detail={"fields": ["reason"]})
    if not payload.notes.strip():
        raise HTTPException(status_code=422, detail={"fields": ["notes"], "message": "notes are required"})
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        res = await conn.execute(text(
            "UPDATE leads SET stage='rejected', reject_reason=:r, reject_notes=:n, rejected_at=now() WHERE id=:id"),
            {"r": payload.reason, "n": payload.notes.strip(), "id": lead_id})
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
    return {"status": "ok"}


@router.post("/leads/sync")
async def sync_leads():
    result = await run_leads_sync(trigger="manual")
    if result["status"] == "not_configured":
        raise HTTPException(status_code=503, detail=result.get("detail"))
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result.get("detail"))
    return result


# --- editable source-captured card ------------------------------------------

class SourceDataPatch(BaseModel):
    city: str | None = None
    society: str | None = None
    configuration: str | None = None
    budget_band: str | None = None
    plan_to_buy: str | None = None
    source_remarks: str | None = None


@router.patch("/leads/{lead_id}/source-data")
async def patch_source_data(lead_id: UUID, payload: SourceDataPatch):
    sets, params = [], {"id": lead_id}
    for field in ("city", "society", "configuration", "budget_band", "plan_to_buy", "source_remarks"):
        val = getattr(payload, field)
        if val is not None:
            sets.append(f"{field} = :{field}")
            params[field] = val or None
    if not sets:
        return {"status": "noop"}
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        res = await conn.execute(text(f"UPDATE leads SET {', '.join(sets)} WHERE id = :id"), params)
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
    return {"status": "ok"}


# --- remarks thread ----------------------------------------------------------

@router.get("/leads/{lead_id}/notes")
async def list_notes(lead_id: UUID):
    """Seed messages from the sheet's Remarks / Remarks 2 + appended notes, oldest first."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.connect() as conn:
        lead = (await conn.execute(
            text("SELECT source_remarks, received_at, source FROM leads WHERE id = :id"), {"id": lead_id}
        )).mappings().first()
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        notes = (await conn.execute(
            text("SELECT id, body, author, source, created_at FROM lead_notes WHERE lead_id = :id ORDER BY created_at"),
            {"id": lead_id},
        )).mappings().all()

    thread = []
    if lead["source_remarks"]:
        for part in [p.strip() for p in lead["source_remarks"].split(" | ") if p.strip()]:
            thread.append({
                "id": None, "body": part, "author": f"From {lead['source']}", "source": "remarks",
                "created_at": lead["received_at"].isoformat() if lead["received_at"] else None,
            })
    for n in notes:
        thread.append({
            "id": str(n["id"]), "body": n["body"], "author": n["author"], "source": n["source"],
            "created_at": n["created_at"].isoformat() if n["created_at"] else None,
        })
    return {"items": thread}


class NoteCreate(BaseModel):
    body: str


@router.post("/leads/{lead_id}/notes")
async def add_note(lead_id: UUID, payload: NoteCreate, user: dict = Depends(current_user)):
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="empty note")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    author = user.get("name") or user.get("email") or "You"
    async with engine.begin() as conn:
        exists = (await conn.execute(text("SELECT 1 FROM leads WHERE id = :id"), {"id": lead_id})).first()
        if exists is None:
            raise HTTPException(status_code=404, detail="lead not found")
        await conn.execute(pg_insert(LeadNote).values(lead_id=lead_id, body=body, author=author, source="note"))
    return {"status": "ok"}


# --- visit planner -------------------------------------------------------------

class VisitStop(BaseModel):
    inventory_id: int | None = None
    name: str | None = None
    society: str | None = None
    locality: str | None = None
    price_text: str | None = None
    lat: float | None = None
    lng: float | None = None


class VisitPlan(BaseModel):
    trip_date: str | None = None
    rm: str | None = None
    start_lat: float | None = None
    start_lng: float | None = None
    total_km: float | None = None
    total_min: float | None = None
    route_source: str | None = None
    stops: list[VisitStop] = []


@router.post("/leads/{lead_id}/visits")
async def save_visit(lead_id: UUID, payload: VisitPlan):
    if not payload.stops:
        raise HTTPException(status_code=422, detail="add at least one stop")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    trip = None
    if payload.trip_date:
        try:
            trip = date.fromisoformat(payload.trip_date)
        except ValueError:
            trip = None
    async with engine.begin() as conn:
        if (await conn.execute(text("SELECT 1 FROM leads WHERE id = :id"), {"id": lead_id})).first() is None:
            raise HTTPException(status_code=404, detail="lead not found")
        await conn.execute(pg_insert(Visit).values(
            lead_id=lead_id, trip_date=trip, rm=payload.rm,
            start_lat=payload.start_lat, start_lng=payload.start_lng,
            total_km=payload.total_km, total_min=payload.total_min, route_source=payload.route_source,
            stops=[s.model_dump() for s in payload.stops],
        ))
        # This is an internal trip plan, NOT an appointment with the buyer — mark it
        # 'visit_planned' (Trip Planned). Only a real Openhouse booking sets
        # 'visit_scheduled' (see POST /v1/visits/book), which is what drives Pipeline.
        # Never downgrade a lead that already has a booked visit or is terminal.
        await conn.execute(text(
            "UPDATE leads SET stage = CASE WHEN stage IN "
            "('won','lost','future_prospect','timepass','rejected','rnr','visit_scheduled') "
            "THEN stage ELSE 'visit_planned' END WHERE id = :id"), {"id": lead_id})
    return {"status": "ok"}


@router.get("/leads/{lead_id}/visits")
async def latest_visit(lead_id: UUID):
    engine = neon_engine()
    if engine is None:
        return {"plan": None}
    async with engine.connect() as conn:
        v = (await conn.execute(text(
            "SELECT * FROM visits WHERE lead_id = :id ORDER BY created_at DESC LIMIT 1"), {"id": lead_id})).mappings().first()
    if v is None:
        return {"plan": None}
    return {"plan": {
        "trip_date": v["trip_date"].isoformat() if v["trip_date"] else None, "rm": v["rm"],
        "start_lat": float(v["start_lat"]) if v["start_lat"] is not None else None,
        "start_lng": float(v["start_lng"]) if v["start_lng"] is not None else None,
        "total_km": float(v["total_km"]) if v["total_km"] is not None else None,
        "total_min": float(v["total_min"]) if v["total_min"] is not None else None,
        "route_source": v["route_source"], "stops": v["stops"],
        "created_at": v["created_at"].isoformat() if v["created_at"] else None,
    }}


# --- assignment ---------------------------------------------------------------

@router.get("/assignees")
async def list_assignees():
    """Active non-admin users a lead can be assigned to (admins don't work leads)."""
    engine = neon_engine()
    if engine is None:
        return {"items": []}
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT name, email FROM users WHERE active AND name IS NOT NULL AND role <> 'admin' ORDER BY name"))
        return {"items": [{"name": r[0], "email": r[1]} for r in res]}


class AssignPayload(BaseModel):
    assigned_to: str | None = None  # null → unassign


@router.post("/leads/{lead_id}/assign")
async def assign_lead(lead_id: UUID, payload: AssignPayload):
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    name = (payload.assigned_to or "").strip() or None
    async with engine.begin() as conn:
        res = await conn.execute(text("UPDATE leads SET assigned_to = :a WHERE id = :id"), {"a": name, "id": lead_id})
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
    return {"status": "ok", "assigned_to": name}


class BulkAssign(BaseModel):
    lead_ids: list[UUID]
    assigned_to: str | None = None  # null → unassign all


@router.post("/leads/bulk-assign")
async def bulk_assign(payload: BulkAssign):
    if not payload.lead_ids:
        raise HTTPException(status_code=422, detail="no leads selected")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    name = (payload.assigned_to or "").strip() or None
    async with engine.begin() as conn:
        res = await conn.execute(
            text("UPDATE leads SET assigned_to = :a WHERE id = ANY(:ids)"),
            {"a": name, "ids": payload.lead_ids},
        )
    return {"status": "ok", "updated": res.rowcount, "assigned_to": name}


# --- master_societies autocomplete -------------------------------------------

@router.get("/societies/search")
async def societies_search(q: str = Query("", min_length=0)):
    return {"items": await search_societies(q)}


@router.get("/localities/search")
async def localities_search(q: str = Query("", min_length=0)):
    return {"items": await search_localities(q)}


@router.get("/micromarkets/search")
async def micromarkets_search(q: str = Query("", min_length=0)):
    return {"items": await search_micromarkets(q)}


@router.get("/localities/by-micromarket")
async def localities_by_mm(micro_market: str = Query(...)):
    """All localities inside a micro-market (for cascade auto-populate)."""
    return {"items": await localities_in_micromarket(micro_market)}


@router.get("/societies/by-locality")
async def societies_by_locality(locality: str = Query(...)):
    """All societies inside a locality (for cascade auto-populate)."""
    return {"items": await societies_in_locality(locality)}
