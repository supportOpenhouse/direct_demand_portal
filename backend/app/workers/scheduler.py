import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

log = logging.getLogger("scheduler")
_scheduler: AsyncIOScheduler | None = None


def start_scheduler(interval_minutes: int) -> None:
    global _scheduler
    if _scheduler is not None:
        return
    from ..services.inventory_sync import run_sync

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
    _scheduler.start()
    log.info("inventory sync scheduled every %d min", interval_minutes)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
