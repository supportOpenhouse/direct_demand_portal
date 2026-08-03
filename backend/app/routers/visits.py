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
    # SMID of the RM accompanying the visit; omitted → the caller's own
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

    # sales_manager_id is the RM ACCOMPANYING the visit, not the lead's RM and not
    # necessarily whoever clicked Book — the planner sends it explicitly. Falling back
    # to the caller keeps older clients working.
    smid = req.sales_manager_id or await _user_smid(user)
    if smid is None:
        raise HTTPException(status_code=403, detail="You're not set up to book visits — ask an admin to add your Openhouse SMID in Settings.")

    log.info("book: user=%s smid=%s (accompanying) n=%s date=%s slot=%s",
             user.get("email"), smid, len(req.visits), req.selected_date, req.selected_time)
    results = await book_visits(smid, req.selected_date, req.selected_time, req.source, [v.model_dump() for v in req.visits])
    booked = sum(1 for r in results if r["ok"])

    # persist each successful booking so the Pipeline tab can track it and the sheet sync
    # can update its status. Fail-soft: a storage hiccup must not lose the booking result.
    if req.lead_id:
        by_home = {v.home_id: v for v in req.visits}
        rows = [
            {
                "lead_id": req.lead_id, "visit_id": r["visit_id"], "home_id": r["home_id"],
                "society": (by_home.get(r["home_id"]).society if by_home.get(r["home_id"]) else None),
                "city": (by_home.get(r["home_id"]).city if by_home.get(r["home_id"]) else None),
                "selected_date": req.selected_date, "selected_time": req.selected_time,
                "status": "upcoming", "booked_by": user.get("email"),
            }
            for r in results if r.get("ok") and r.get("visit_id")
        ]
        if rows:
            try:
                engine = neon_engine()
                async with engine.begin() as conn:
                    await conn.execute(
                        pg_insert(CrmVisit).values(rows).on_conflict_do_nothing(index_elements=["visit_id"])
                    )
                    # a real booking is the ONLY thing that means "Visit Scheduled"
                    # (this is also what moves the lead into Pipeline)
                    await conn.execute(text(
                        "UPDATE leads SET stage = CASE WHEN stage IN "
                        "('won','rejected','rnr') "
                        "THEN stage ELSE 'visit_scheduled' END WHERE id = :id"), {"id": req.lead_id})
            except Exception:  # noqa: BLE001
                log.exception("failed to persist booked visits (booking itself succeeded)")

    return {"booked": booked, "failed": len(results) - booked, "results": results}
