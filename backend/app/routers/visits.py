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

    # A second visit to the SAME home can't be booked while the first is still pending —
    # that one is a revisit and the earlier visit has to be completed or cancelled first.
    # A visit to a DIFFERENT property is a normal new visit and is always allowed, which
    # is what "+ New visit" in Manage Visits relies on.
    seen_homes: set[int] = set()
    if req.lead_id:
        engine = neon_engine()
        if engine is not None:
            homes = [v.home_id for v in req.visits]
            async with engine.connect() as conn:
                clash = (await conn.execute(text(
                    "SELECT society FROM crm_visits WHERE lead_id = :id AND status = 'upcoming' "
                    "AND home_id = ANY(:homes) LIMIT 1"),
                    {"id": req.lead_id, "homes": homes})).first()
                # every property this lead has EVER had a visit to — decides revisit below
                seen_homes = {r[0] for r in (await conn.execute(text(
                    "SELECT DISTINCT home_id FROM crm_visits WHERE lead_id = :id AND home_id IS NOT NULL"),
                    {"id": req.lead_id})).all()}
            if clash:
                raise HTTPException(status_code=409,
                    detail=f"This lead already has an upcoming visit to {clash[0] or 'this property'} — "
                           "complete or cancel it before booking another one there.")

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
                    # A real booking is the ONLY thing that schedules a visit.
                    # ⚠️ A REVISIT is the same buyer returning to the SAME property — not
                    # simply a lead with more than one visit. A lead touring three
                    # different societies has three first visits, so it stays
                    # visit_scheduled; going back to one it has already seen is what
                    # makes it revisit_scheduled (Pipeline Leads).
                    is_revisit = any(r["home_id"] in seen_homes for r in rows)
                    # Forward-only: terminal leads keep their stage, and a lead already in
                    # the pipeline is never demoted back to visit_scheduled.
                    moved = (await conn.execute(text(
                        "UPDATE leads SET stage = CASE "
                        "WHEN stage IN ('won','future_prospect','rejected','rnr') THEN stage "
                        "WHEN :is_revisit THEN 'revisit_scheduled' "
                        "WHEN stage = 'revisit_scheduled' THEN stage "
                        "ELSE 'visit_scheduled' END WHERE id = :id "
                        "RETURNING (SELECT stage FROM leads WHERE id = :id) AS before, stage"),
                        {"id": req.lead_id, "is_revisit": is_revisit})).first()

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


# --- manage visits: one visit at a time -------------------------------------------
# Cancel / complete / reschedule / revisit. Each mirrors the Core call into crm_visits
# so the lead's visit list stays true without waiting for the next sheet sync.


class SlotIn(BaseModel):
    selected_date: str
    selected_time: str


class CompleteIn(BaseModel):
    sales_feedback: str = ""
    lead_status: str | None = None
    # the six sm_demand_feedback keys; blank answers are dropped by the service
    sm_feedback: dict[str, str] | None = None


async def _visit_row(visit_id: int) -> dict | None:
    """Our crm_visits row for a Core visit id."""
    engine = neon_engine()
    if engine is None:
        return None
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT lead_id, home_id, society, city, status, buyer_name, buyer_mobile, "
            "selected_date, selected_time, smid, rm_accompanying, source "
            "FROM crm_visits WHERE visit_id = :v"), {"v": visit_id})).mappings().first()
    return dict(row) if row else None


def _require_booking_configured() -> None:
    if not get_settings().crm_booking_configured:
        raise HTTPException(status_code=503,
            detail="Visit booking isn't configured yet (CRM_BOOKING_API_BASE_URL / CRM_API_KEY).")


async def _known_visit(visit_id: int) -> dict:
    _require_booking_configured()
    row = await _visit_row(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="We have no record of that visit.")
    return row


async def _apply(visit_id: int, sets: str, params: dict, events: list) -> None:
    """Mirror a Core change into crm_visits and log it. Fail-soft: the Core call already
    succeeded, and losing our copy must not report the whole action as failed — the sheet
    sync reconciles it within 30 minutes either way."""
    try:
        engine = neon_engine()
        async with engine.begin() as conn:
            await conn.execute(text(f"UPDATE crm_visits SET {sets} WHERE visit_id = :v"),
                               {"v": visit_id, **params})
            if events:
                await activity.record(conn, events)
    except Exception:  # noqa: BLE001
        log.exception("visit %s: Core updated but our copy didn't", visit_id)


@router.post("/visits/{visit_id}/cancel")
async def cancel(visit_id: int, user: dict = Depends(current_user)):
    """Cancel an upcoming visit on Core. The lead's stage is left alone — stage moves are
    forward-only, and a cancelled visit doesn't un-happen the ones before it."""
    row = await _known_visit(visit_id)
    from ..services.crm_booking import cancel_visit

    res = await cancel_visit(visit_id)
    if res["status"] == "error":
        raise HTTPException(status_code=502, detail=res["detail"])

    events = []
    if row["lead_id"]:
        events.append(activity.row_for(
            activity.Actor.of(user), entity_type="lead", entity_id=row["lead_id"],
            action="visit_cancelled",
            metadata={"visit_id": visit_id, "society": row["society"]}))
    await _apply(visit_id, "status = 'cancelled', synced_at = now()", {}, events)
    log.info("cancel visit=%s by=%s", visit_id, user.get("email"))
    return {"ok": True, "visit_id": visit_id, "status": "cancelled"}


@router.post("/visits/{visit_id}/complete")
async def complete(visit_id: int, req: CompleteIn, user: dict = Depends(current_user)):
    """Mark a visit completed on Core, with the SM's feedback form."""
    row = await _known_visit(visit_id)
    from ..services.crm_booking import LEAD_STATUS_VALUES, complete_visit

    if req.lead_status and req.lead_status not in LEAD_STATUS_VALUES:
        raise HTTPException(status_code=400,
            detail=f"Invalid lead status. Use one of: {', '.join(LEAD_STATUS_VALUES)}")

    res = await complete_visit(visit_id, req.sales_feedback, req.lead_status, req.sm_feedback)
    if res["status"] == "error":
        raise HTTPException(status_code=502, detail=res["detail"])

    events = []
    if row["lead_id"]:
        events.append(activity.row_for(
            activity.Actor.of(user), entity_type="lead", entity_id=row["lead_id"],
            action="visit_completed",
            metadata={"visit_id": visit_id, "society": row["society"],
                      "lead_status": req.lead_status}))
    # visit_date is Core's — it stamps the day the visit was marked done
    await _apply(visit_id,
                 "status = 'completed', sales_feedback = :f, "
                 "visit_date = coalesce(:d, visit_date), synced_at = now()",
                 {"f": req.sales_feedback or None,
                  "d": (res.get("visit") or {}).get("visitDate")}, events)
    log.info("complete visit=%s lead_status=%s by=%s", visit_id, req.lead_status, user.get("email"))
    return {"ok": True, "visit_id": visit_id, "status": "completed"}


@router.post("/visits/{visit_id}/reschedule")
async def reschedule(visit_id: int, req: SlotIn, user: dict = Depends(current_user)):
    """Move an upcoming visit to a new slot. Same visit id, so nothing about the lead's
    history changes — only when they're going."""
    row = await _known_visit(visit_id)
    from ..services.crm_booking import SLOT_VALUES, reschedule_visit

    if req.selected_time not in SLOT_VALUES:
        raise HTTPException(status_code=400, detail=f"Invalid time slot. Use one of: {', '.join(SLOT_VALUES)}")

    res = await reschedule_visit(visit_id, req.selected_date, req.selected_time)
    if res["status"] == "error":
        raise HTTPException(status_code=502, detail=res["detail"])

    events = []
    if row["lead_id"]:
        events.append(activity.row_for(
            activity.Actor.of(user), entity_type="lead", entity_id=row["lead_id"],
            action="visit_rescheduled",
            before=f"{row['selected_date']} {row['selected_time']}",
            after=f"{req.selected_date} {req.selected_time}",
            metadata={"visit_id": visit_id, "society": row["society"]}))
    await _apply(visit_id, "selected_date = :d, selected_time = :t, status = 'upcoming', synced_at = now()",
                 {"d": req.selected_date, "t": req.selected_time}, events)
    log.info("reschedule visit=%s -> %s %s by=%s", visit_id, req.selected_date, req.selected_time, user.get("email"))
    return {"ok": True, "visit_id": visit_id, "selected_date": req.selected_date,
            "selected_time": req.selected_time}


@router.post("/visits/{visit_id}/revisit")
async def revisit(visit_id: int, req: SlotIn, user: dict = Depends(current_user)):
    """Book the same buyer back into the SAME property — a new visit cloned from this
    completed one. Core copies the buyer, home, broker and sales manager, and returns a
    NEW visit id, so this always moves the lead to revisit_scheduled."""
    row = await _known_visit(visit_id)
    from ..services.crm_booking import SLOT_VALUES, create_revisit

    if req.selected_time not in SLOT_VALUES:
        raise HTTPException(status_code=400, detail=f"Invalid time slot. Use one of: {', '.join(SLOT_VALUES)}")

    res = await create_revisit(visit_id, req.selected_date, req.selected_time)
    if res["status"] == "error":
        raise HTTPException(status_code=502, detail=res["detail"])
    new_id = (res.get("visit") or {}).get("id")
    if not new_id:
        raise HTTPException(status_code=502, detail="Openhouse accepted the revisit but returned no visit id.")

    # Same property by definition, so this row is a copy of the original with the new
    # id and slot. Fail-soft for the same reason as _apply.
    try:
        engine = neon_engine()
        async with engine.begin() as conn:
            await conn.execute(pg_insert(CrmVisit).values([{
                "lead_id": row["lead_id"], "visit_id": new_id, "home_id": row["home_id"],
                "society": row["society"], "city": row["city"],
                "buyer_name": row["buyer_name"], "buyer_mobile": row["buyer_mobile"],
                "selected_date": req.selected_date, "selected_time": req.selected_time,
                "source": row["source"], "smid": row["smid"],
                "rm_accompanying": row["rm_accompanying"],
                "status": "upcoming", "booked_by": user.get("email"),
            }]).on_conflict_do_nothing(index_elements=["visit_id"]))

            events = []
            if row["lead_id"]:
                actor = activity.Actor.of(user)
                events.append(activity.row_for(
                    actor, entity_type="lead", entity_id=row["lead_id"],
                    action="visit_booked",
                    metadata={"visits": 1, "revisit_of": visit_id, "visit_id": new_id,
                              "society": row["society"]}))
                moved = (await conn.execute(text(
                    "UPDATE leads SET stage = CASE "
                    "WHEN stage IN ('won','future_prospect','rejected','rnr') THEN stage "
                    "ELSE 'revisit_scheduled' END WHERE id = :id "
                    "RETURNING (SELECT stage FROM leads WHERE id = :id) AS before, stage"),
                    {"id": row["lead_id"]})).first()
                if moved and moved[0] != moved[1]:
                    events.append(activity.row_for(
                        actor, entity_type="lead", entity_id=row["lead_id"],
                        action="stage_change", field="stage", before=moved[0], after=moved[1],
                        metadata={"via": "revisit"}))
            if events:
                await activity.record(conn, events)
    except Exception:  # noqa: BLE001
        log.exception("revisit %s->%s: Core booked it but our copy didn't", visit_id, new_id)

    log.info("revisit visit=%s -> new=%s %s %s by=%s", visit_id, new_id,
             req.selected_date, req.selected_time, user.get("email"))
    return {"ok": True, "visit_id": new_id, "revisit_of": visit_id,
            "selected_date": req.selected_date, "selected_time": req.selected_time}
