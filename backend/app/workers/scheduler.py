import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

log = logging.getLogger("scheduler")
_scheduler: AsyncIOScheduler | None = None


def start_scheduler(interval_minutes: int, leads_interval_hours: int = 4) -> None:
    global _scheduler
    if _scheduler is not None:
        return
    from ..services.inventory_sync import run_sync
    from ..services.leads_sync import run_leads_sync

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_sync,
        "interval",
        minutes=max(1, interval_minutes),
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="inventory_sync",
    )
    # leads ingest is insert-only — adds new leads, never updates or deletes
    _scheduler.add_job(
        run_leads_sync,
        "interval",
        hours=max(1, leads_interval_hours),
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="leads_sync",
    )
    _scheduler.start()
    log.info("inventory sync every %d min; leads ingest every %d h", interval_minutes, leads_interval_hours)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
