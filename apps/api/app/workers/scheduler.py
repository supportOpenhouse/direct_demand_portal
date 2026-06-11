"""Background jobs (APScheduler):
- tat_sweep        every 5 min: alert once per unconfirmed lead past its TAT deadline
- reminders_due    every 5 min: stub-notify due reminders, mark notified
- goldmine_rematch nightly:     full bucket rebuild

Runs in-process inside FastAPI when RUN_SCHEDULER=true, or standalone via
`python -m app.workers.scheduler` (future Render worker split).
"""
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import exists, select

from app.core.utils import utcnow
from app.db import SessionLocal
from app.models import Lead, LeadActivity, Reminder
from app.services import goldmine, whatsapp

log = logging.getLogger("app.scheduler")


async def tat_sweep() -> None:
    async with SessionLocal() as session:
        now = utcnow()
        breach_logged = (
            select(LeadActivity.id)
            .where(LeadActivity.lead_id == Lead.id, LeadActivity.event == "tat_breach")
            .exists()
        )
        stmt = select(Lead).where(
            Lead.confirmed.is_(False),
            Lead.tat_deadline.is_not(None),
            Lead.tat_deadline < now,
            ~breach_logged,
        )
        leads = (await session.execute(stmt)).scalars().all()
        for lead in leads:
            whatsapp.stub_send(
                session,
                lead,
                f"⚠️ TAT breached for {lead.name} — first contact overdue.",
                event="tat_breach",
            )
        if leads:
            await session.commit()
            log.info("tat_sweep: flagged %d breach(es)", len(leads))


async def reminders_due() -> None:
    async with SessionLocal() as session:
        now = utcnow()
        stmt = select(Reminder).where(
            Reminder.done.is_(False), Reminder.notified.is_(False), Reminder.due_at <= now
        )
        due = (await session.execute(stmt)).scalars().all()
        for reminder in due:
            log.info(
                "REMINDER STUB notify: [%s] %s for lead %s due %s",
                reminder.type,
                reminder.note or "",
                reminder.lead.name if reminder.lead is not None else reminder.lead_id,
                reminder.due_at,
            )
            reminder.notified = True
        if due:
            await session.commit()
            log.info("reminders_due: notified %d reminder(s)", len(due))


async def goldmine_rematch() -> None:
    async with SessionLocal() as session:
        n = await goldmine.rematch(session)
        log.info("nightly goldmine rematch: %d bucket(s)", n)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(tat_sweep, "interval", minutes=5, id="tat_sweep", max_instances=1)
    scheduler.add_job(reminders_due, "interval", minutes=5, id="reminders_due", max_instances=1)
    # 21:30 UTC = 03:00 IST
    scheduler.add_job(goldmine_rematch, "cron", hour=21, minute=30, id="goldmine_rematch")
    return scheduler


async def _run_standalone() -> None:
    logging.basicConfig(level=logging.INFO)
    scheduler = build_scheduler()
    scheduler.start()
    log.info("standalone scheduler running — Ctrl-C to stop")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(_run_standalone())
