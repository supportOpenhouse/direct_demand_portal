import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import apply_lead_scope, get_current_user
from app.core.errors import ApiError
from app.db import get_session
from app.models import Lead, Reminder, User
from app.schemas.requests import ReminderCreate, ReminderPatch, ReminderType
from app.services.serializers import reminder_payload

router = APIRouter(tags=["reminders"])


@router.get("/reminders")
async def list_reminders(
    type: ReminderType | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = apply_lead_scope(
        select(Reminder).join(Lead, Reminder.lead_id == Lead.id), user
    ).order_by(Reminder.due_at.asc())
    if type is not None:
        stmt = stmt.where(Reminder.type == type)
    reminders = (await session.execute(stmt)).scalars().all()
    return [reminder_payload(r) for r in reminders]


@router.post("/reminders", status_code=201)
async def create_reminder(
    payload: ReminderCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lead_stmt = apply_lead_scope(select(Lead).where(Lead.id == payload.lead_id), user)
    lead = (await session.execute(lead_stmt)).scalar_one_or_none()
    if lead is None:
        raise ApiError(404, "Lead not found")
    reminder = Reminder(
        id=uuid.uuid4(),
        lead_id=lead.id,
        type=payload.type,
        note=payload.note,
        due_at=payload.due_at,
        done=False,
        auto_generated=False,
    )
    session.add(reminder)
    await session.commit()
    reminder = (
        await session.execute(
            select(Reminder).where(Reminder.id == reminder.id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    return reminder_payload(reminder)


@router.patch("/reminders/{reminder_id}")
async def patch_reminder(
    reminder_id: uuid.UUID,
    payload: ReminderPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = apply_lead_scope(
        select(Reminder).join(Lead, Reminder.lead_id == Lead.id).where(Reminder.id == reminder_id),
        user,
    )
    reminder = (await session.execute(stmt)).scalar_one_or_none()
    if reminder is None:
        raise ApiError(404, "Reminder not found")
    if payload.done is not None:
        reminder.done = payload.done
    await session.commit()
    return reminder_payload(reminder)
