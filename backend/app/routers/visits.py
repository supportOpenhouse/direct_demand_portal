"""Visit booking on the Openhouse app (server-to-server). Resolves the booker's
SalesManager id (smid) from the logged-in user; derives the CP/broker per unit city."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from ..config import get_settings
from ..core.auth import current_user
from ..db import neon_engine
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


@router.get("/visits/booking-config")
async def booking_config(user: dict = Depends(current_user)):
    """Tells the drawer whether the current user can book + the city→CP labels to show."""
    s = get_settings()
    smid = await _user_smid(user)
    return {
        "configured": s.crm_booking_configured,
        "smid": smid,
        "can_book": s.crm_booking_configured and smid is not None,
        "default_source": DEFAULT_SOURCE,
        "city_cp": {city: {"cp_id": cp, "label": label} for city, (cp, label) in BROKER_BY_CITY.items()},
    }


class BookVisitIn(BaseModel):
    home_id: int
    city: str | None = None
    buyer_name: str
    buyer_mobile: str


class BookRequest(BaseModel):
    selected_date: str
    selected_time: str
    source: str = DEFAULT_SOURCE
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

    smid = await _user_smid(user)
    if smid is None:
        raise HTTPException(status_code=403, detail="You're not set up to book visits — ask an admin to add your Openhouse SMID in Settings.")

    log.info("book: user=%s smid=%s n=%s date=%s slot=%s", user.get("email"), smid, len(req.visits), req.selected_date, req.selected_time)
    results = await book_visits(smid, req.selected_date, req.selected_time, req.source, [v.model_dump() for v in req.visits])
    booked = sum(1 for r in results if r["ok"])
    return {"booked": booked, "failed": len(results) - booked, "results": results}
