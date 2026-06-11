import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import apply_lead_scope, get_current_user
from app.core.errors import ApiError
from app.db import get_session
from app.models import Interest, Lead, LeadActivity, SupplyUnit, User
from app.schemas.requests import InterestCreate
from app.services.serializers import unit_payload

router = APIRouter(tags=["supply"])


@router.get("/supply")
async def list_supply(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    counts = dict(
        (
            await session.execute(
                select(Interest.supply_unit_id, func.count()).group_by(Interest.supply_unit_id)
            )
        ).all()
    )
    units = (
        (await session.execute(select(SupplyUnit).order_by(SupplyUnit.city, SupplyUnit.name)))
        .scalars()
        .all()
    )
    return [unit_payload(u, "supply", counts.get(u.id, 0)) for u in units]


@router.post("/supply/{unit_id}/interest", status_code=201)
async def tag_interest(
    unit_id: uuid.UUID,
    payload: InterestCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    unit = await session.get(SupplyUnit, unit_id)
    if unit is None:
        raise ApiError(404, "Supply unit not found")
    if payload.lead_id is not None:
        lead_stmt = apply_lead_scope(select(Lead).where(Lead.id == payload.lead_id), user)
        lead = (await session.execute(lead_stmt)).scalar_one_or_none()
        if lead is None:
            raise ApiError(404, "Lead not found")
        session.add(
            LeadActivity(
                lead_id=lead.id,
                event="interest_tagged",
                remark=f"Tagged as buyer for {unit.name} ({unit.society})",
                actor_id=user.id,
            )
        )
    session.add(
        Interest(supply_unit_id=unit.id, lead_id=payload.lead_id, rm_id=user.id, note=payload.note)
    )
    await session.commit()
    count = (
        await session.execute(
            select(func.count()).select_from(Interest).where(Interest.supply_unit_id == unit.id)
        )
    ).scalar_one()
    return {"interest_count": count}
