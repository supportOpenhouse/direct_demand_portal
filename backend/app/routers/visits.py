"""Visit booking on the Openhouse app (server-to-server). Resolves the booker's
SalesManager id (smid) from the logged-in user; derives the CP/broker per unit city."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..core.auth import current_user
from ..db import neon_engine
from ..models import CrmVisit
from ..services import activity
from ..services.crm_booking import BROKER_BY_CITY, DEFAULT_SOURCE, SLOT_VALUES, book_visits

log = logging.getLogger("visits")
router = APIRouter(tags=["visits"], dependencies=[Depends(current_user)])


async def _user_smid(user: dict) -> int | None:
    """The logged-in user's Openhouse SalesManager id, or None if unmapped."""
    engine = neon_engine()
    if engine is None or not user.get("email"):
        return None
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT smid FROM users WHERE lower(email) = :e"), {"e": user["email"].lower()}
        )).first()
    return row[0] if row and row[0] is not None else None


async def _smid_for_name(name: str | None) -> int | None:
    """The Openhouse SMID of the RM with this name (active, mapped). Used to resolve the
    accompanying RM's smid server-side so the booking is always attributed to them."""
    engine = neon_engine()
    if engine is None or not name or not name.strip():
        return None
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT smid FROM users WHERE lower(name) = lower(:n) AND active AND smid IS NOT NULL LIMIT 1"),
            {"n": name.strip()})).first()
    return row[0] if row else None


@router.post("/visits/sync")
async def sync_visit_status():
    """Pull the latest status (upcoming | completed | cancelled) for every visit we booked."""
    from ..services.visits_sync import run_visits_sync

    result = await run_visits_sync(trigger="manual")
    if result["status"] == "not_configured":
        raise HTTPException(status_code=503, detail=result.get("detail"))
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result.get("detail"))
    return result


async def _bookable_managers() -> list[dict]:
    """Active users who hold an Openhouse SMID. Only these can be the accompanying RM —
    the booking API takes a SalesManager id, so a name without one can't be sent."""
    engine = neon_engine()
    if engine is None:
        return []
    async with engine.connect() as conn:
        rows = await conn.execute(text(
            "SELECT name, smid FROM users "
            "WHERE active AND smid IS NOT NULL AND name IS NOT NULL ORDER BY name"))
    return [{"name": r[0], "smid": r[1]} for r in rows]


@router.get("/visits/booking-config")
async def booking_config(user: dict = Depends(current_user)):
    """Tells the drawer whether the current user can book + the city→CP labels to show."""
    s = get_settings()
    smid = await _user_smid(user)
    return {
        "configured": s.crm_booking_configured,
        "smid": smid,
        "can_book": s.crm_booking_configured and smid is not None,
        "bookable": await _bookable_managers(),
        "default_source": DEFAULT_SOURCE,
        "city_cp": {city: {"cp_id": cp, "label": label} for city, (cp, label) in BROKER_BY_CITY.items()},
    }


class BookVisitIn(BaseModel):
    home_id: int
    city: str | None = None
    buyer_name: str
    buyer_mobile: str
    society: str | None = None


class BookRequest(BaseModel):
    selected_date: str
    selected_time: str
    source: str = DEFAULT_SOURCE
    # the RM accompanying the visit — the booking is attributed to THEM. The name is
    # authoritative (server resolves their smid); sales_manager_id is a legacy fallback.
    rm_accompanying: str | None = None
    sales_manager_id: int | None = None
    lead_id: UUID | None = None   # links the booking to a lead → drives the Pipeline tab
    visits: list[BookVisitIn]


@router.post("/visits/book")
async def book(req: BookRequest, user: dict = Depends(current_user)):
    s = get_settings()
    if not s.crm_booking_configured:
        raise HTTPException(status_code=503, detail="Visit booking isn't configured yet (CRM_BOOKING_API_BASE_URL / CRM_API_KEY).")
    if not req.visits:
        raise HTTPException(status_code=400, detail="No visits to book")
    if len(req.visits) > 10:
        raise HTTPException(status_code=400, detail="At most 10 visits per booking")
    if req.selected_time not in SLOT_VALUES:
        raise HTTPException(status_code=400, detail=f"Invalid time slot. Use one of: {', '.join(SLOT_VALUES)}")
    for v in req.visits:
        if not v.buyer_name.strip() or len(v.buyer_mobile.strip()) < 5:
            raise HTTPException(status_code=400, detail="Each visit needs a buyer name and at least 5 mobile digits")

    # The smid sent to Core MUST be the accompanying RM's — resolve it authoritatively
    # from their name so the visit is always attributed to them (never to whoever clicked
    # Book). No SMID for that RM → we can't book, rather than silently mis-attribute.
    if req.rm_accompanying:
        smid = await _smid_for_name(req.rm_accompanying)
        if smid is None:
            raise HTTPException(status_code=403,
                detail=f"{req.rm_accompanying} has no Openhouse SMID — ask an admin to add it in Settings before booking.")
    else:
        smid = req.sales_manager_id  # legacy client that sends only the id
        if smid is None:
            raise HTTPException(status_code=403, detail="Pick an accompanying RM who has an Openhouse SMID before booking.")

    # A revisit can't be booked while a prior visit is still pending — the previous one
    # must be marked complete (via the ops-sheet sync) first.
    if req.lead_id:
        engine = neon_engine()
        if engine is not None:
            async with engine.connect() as conn:
                pending = (await conn.execute(text(
                    "SELECT count(*) FROM crm_visits WHERE lead_id = :id AND status = 'upcoming'"),
                    {"id": req.lead_id})).scalar()
            if pending:
                raise HTTPException(status_code=409,
                    detail="This lead has a visit that isn't marked complete yet — complete it before booking a revisit.")

    log.info("book: user=%s smid=%s (accompanying=%s) n=%s date=%s slot=%s",
             user.get("email"), smid, req.rm_accompanying, len(req.visits), req.selected_date, req.selected_time)
    results = await book_visits(smid, req.selected_date, req.selected_time, req.source, [v.model_dump() for v in req.visits])
    booked = sum(1 for r in results if r["ok"])

    # persist each successful booking so the Pipeline tab can track it and the sheet sync
    # can update its status. Fail-soft: a storage hiccup must not lose the booking result.
    if req.lead_id:
        by_home = {v.home_id: v for v in req.visits}
        rows = []
        for r in results:
            if not (r.get("ok") and r.get("visit_id")):
                continue
            bh = by_home.get(r["home_id"])
            rows.append({
                "lead_id": req.lead_id, "visit_id": r["visit_id"], "home_id": r["home_id"],
                "society": bh.society if bh else None, "city": bh.city if bh else None,
                "buyer_name": bh.buyer_name if bh else None,
                "buyer_mobile": bh.buyer_mobile if bh else None,
                "selected_date": req.selected_date, "selected_time": req.selected_time,
                "source": req.source, "smid": smid, "rm_accompanying": req.rm_accompanying,
                "status": "upcoming", "booked_by": user.get("email"),
            })
        if rows:
            try:
                engine = neon_engine()
                async with engine.begin() as conn:
                    await conn.execute(
                        pg_insert(CrmVisit).values(rows).on_conflict_do_nothing(index_elements=["visit_id"])
                    )
                    # A real booking is the ONLY thing that schedules a visit. The first
                    # booking → visit_scheduled (Visited Leads). Booking again on a lead
                    # that's already visited = a revisit → revisit_scheduled (Pipeline
                    # Leads). Forward-only: terminal / already-in-pipeline leads are kept.
                    moved = (await conn.execute(text(
                        "UPDATE leads SET stage = CASE "
                        "WHEN stage IN ('won','rejected','rnr','revisit_scheduled') THEN stage "
                        "WHEN stage = 'visit_scheduled' THEN 'revisit_scheduled' "
                        "ELSE 'visit_scheduled' END WHERE id = :id "
                        "RETURNING (SELECT stage FROM leads WHERE id = :id) AS before, stage"),
                        {"id": req.lead_id})).first()

                    actor = activity.Actor.of(user)
                    events = [activity.row_for(
                        actor, entity_type="lead", entity_id=req.lead_id,
                        action="visit_booked",
                        # the booking itself, separate from the stage move: a revisit on
                        # an already-visited lead books a visit but moves no stage
                        metadata={"visits": booked})]
                    # The CASE is forward-only, so a booking on a won/rejected lead
                    # changes nothing — logging the attempt would inflate the report.
                    if moved and moved[0] != moved[1]:
                        events.append(activity.row_for(
                            actor, entity_type="lead", entity_id=req.lead_id,
                            action="stage_change", field="stage",
                            before=moved[0], after=moved[1],
                            metadata={"via": "visit_booking"}))
                    await activity.record(conn, events)
            except Exception:  # noqa: BLE001
                log.exception("failed to persist booked visits (booking itself succeeded)")

    return {"booked": booked, "failed": len(results) - booked, "results": results}
