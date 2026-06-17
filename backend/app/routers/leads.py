from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..core.auth import assignment_aliases, current_user
from ..db import neon_engine
from ..models import Lead, LeadConfirmedData, LeadNote, Visit
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

# segment → SQL predicate on the leads spine
SEGMENTS = {
    "new": "stage = 'new'",
    "qualified": "confirmed = true AND stage NOT IN ('won','lost','future_prospect','timepass') "
                 "AND qualified_at IS NOT NULL AND now() - qualified_at < interval '7 days'",
    "pipeline": "confirmed = true AND stage NOT IN ('won','lost','future_prospect','timepass') "
                "AND qualified_at IS NOT NULL AND now() - qualified_at >= interval '7 days'",
    "converted": "stage = 'won'",
}


def _lead_row(r) -> dict:
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
        "stage": r["stage"],
        "tat_deadline": r["tat_deadline"].isoformat() if r["tat_deadline"] else None,
        "confirmed": r["confirmed"],
        "qualified_at": r["qualified_at"].isoformat() if r["qualified_at"] else None,
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
    # role-scoping: an RM sees their own leads PLUS any unassigned lead (those are
    # up for grabs by everyone). Admin/CM see all.
    params: dict = {}
    if user.get("role") == "rm":
        aliases = assignment_aliases(user)
        if aliases:
            predicate += " AND (assigned_to IS NULL OR lower(assigned_to) = ANY(:aliases))"
            params["aliases"] = aliases
        else:
            predicate += " AND assigned_to IS NULL"
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text(f"SELECT * FROM leads WHERE {predicate} ORDER BY is_test DESC, created_at DESC"), params
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


@router.post("/leads/{lead_id}/confirm")
async def confirm_lead(lead_id: UUID, payload: ConfirmPayload):
    """Save the call form and qualify the lead (new → contacted)."""
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
        # qualify: new → contacted, start the 7-day clock (only on first confirm)
        await conn.execute(
            text(
                "UPDATE leads SET confirmed = true, "
                "stage = CASE WHEN stage = 'new' THEN 'contacted' ELSE stage END, "
                "tat_deadline = NULL, "
                "qualified_at = COALESCE(qualified_at, now()) WHERE id = :id"
            ),
            {"id": lead_id},
        )
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
        # advance to Visit Scheduled unless the lead is already in a terminal stage
        await conn.execute(text(
            "UPDATE leads SET stage = CASE WHEN stage IN ('won','lost','future_prospect','timepass') "
            "THEN stage ELSE 'visit_scheduled' END WHERE id = :id"), {"id": lead_id})
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
    """Active users a lead can be assigned to (for the assign dropdown)."""
    engine = neon_engine()
    if engine is None:
        return {"items": []}
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT name, email FROM users WHERE active AND name IS NOT NULL ORDER BY name"))
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
