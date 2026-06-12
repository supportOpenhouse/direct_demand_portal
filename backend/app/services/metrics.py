from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import lead_scope_filter
from app.core.utils import utcnow
from app.models import Lead, Reminder, User
from app.services.segments import TERMINAL_STAGES, segment_criteria


async def dashboard_metrics(session: AsyncSession, user: User) -> dict:
    now = utcnow()
    crit = lead_scope_filter(user)

    async def count_leads(criteria: list) -> int:
        stmt = select(func.count()).select_from(Lead).where(*criteria)
        if crit is not None:
            stmt = stmt.where(crit)
        return (await session.execute(stmt)).scalar_one()

    # followups due today: not-done reminders due within today's UTC date, lead-scoped
    day_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    followups_stmt = (
        select(func.count())
        .select_from(Reminder)
        .join(Lead, Reminder.lead_id == Lead.id)
        .where(Reminder.done.is_(False), Reminder.due_at >= day_start, Reminder.due_at < day_end)
    )
    if crit is not None:
        followups_stmt = followups_stmt.where(crit)

    return {
        "new": await count_leads(segment_criteria("new", now)),
        "qualified": await count_leads(segment_criteria("qualified", now)),
        "immediate": await count_leads([Lead.is_hot.is_(True), Lead.stage.notin_(TERMINAL_STAGES)]),
        "followups_due_today": (await session.execute(followups_stmt)).scalar_one(),
        "pipeline": await count_leads(segment_criteria("pipeline", now)),
        "converted": await count_leads(segment_criteria("converted", now)),
    }
