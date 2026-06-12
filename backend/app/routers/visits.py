import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import apply_lead_scope, get_current_user
from app.core.errors import ApiError
from app.core.utils import utcnow
from app.db import get_session
from app.models import Inventory, Lead, LeadActivity, Recording, Reminder, User, Visit, VisitStop
from app.routers.leads import fetch_lead
from app.schemas.requests import RecordingCreate, VisitCreate
from app.services.serializers import recording_payload, visit_payload

router = APIRouter(tags=["visits"])


@router.post("/leads/{lead_id}/visits", status_code=201)
async def create_visit(
    lead_id: uuid.UUID,
    payload: VisitCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lead = await fetch_lead(session, lead_id, user)

    inventory_ids = [s.inventory_id for s in payload.stops]
    found = set(
        (await session.execute(select(Inventory.id).where(Inventory.id.in_(inventory_ids)))).scalars()
    )
    unknown = [str(i) for i in inventory_ids if i not in found]
    if unknown:
        raise ApiError(422, "Validation error", {"stops": f"Unknown inventory_id(s): {', '.join(unknown)}"})

    now = utcnow()
    token = secrets.token_urlsafe(16)
    visit = Visit(
        id=uuid.uuid4(),
        lead_id=lead.id,
        trip_date=payload.trip_date,
        rm_id=user.id,
        total_km=payload.total_km,
        total_min=payload.total_min,
        route_source=payload.route_source,
        self_schedule_token=token,
        status="planned",
    )
    session.add(visit)
    for stop in payload.stops:
        session.add(VisitStop(visit_id=visit.id, inventory_id=stop.inventory_id, seq=stop.seq))

    lead.stage = "visit_scheduled"
    # auto visit-feedback reminder +2h (§6.7)
    session.add(
        Reminder(
            lead_id=lead.id,
            type="visit_feedback",
            note=f"Collect visit feedback from {lead.name}",
            due_at=now + timedelta(hours=2),
            done=False,
            auto_generated=True,
        )
    )
    session.add(
        LeadActivity(
            lead_id=lead.id,
            event="visit_scheduled",
            remark=f"{len(payload.stops)}-stop visit planned for {payload.trip_date.isoformat()} "
            f"({payload.total_km:g} km, {payload.total_min:g} min, {payload.route_source})",
            actor_id=user.id,
        )
    )
    await session.commit()
    visit = (
        await session.execute(
            select(Visit).where(Visit.id == visit.id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    return {"visit": visit_payload(visit), "self_schedule_token": token}


@router.post("/visits/{visit_id}/recording", status_code=201)
async def add_recording(
    visit_id: uuid.UUID,
    payload: RecordingCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = apply_lead_scope(
        select(Visit).join(Lead, Visit.lead_id == Lead.id).where(Visit.id == visit_id), user
    )
    visit = (await session.execute(stmt)).scalar_one_or_none()
    if visit is None:
        raise ApiError(404, "Visit not found")
    rec = Recording(
        id=uuid.uuid4(),
        lead_id=visit.lead_id,
        visit_id=visit.id,
        file_ref=payload.file_ref,
        duration_sec=payload.duration_sec,
        recorded_by=user.id,
        recorded_at=utcnow(),
    )
    session.add(rec)
    await session.commit()
    rec = (
        await session.execute(
            select(Recording).where(Recording.id == rec.id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    return recording_payload(rec)
