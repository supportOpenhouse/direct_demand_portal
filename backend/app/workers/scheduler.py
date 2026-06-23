import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..cache import try_acquire_lock

log = logging.getLogger("scheduler")
_scheduler: AsyncIOScheduler | None = None


def locked_job(job_name: str, fn, ttl: int):
    """Wrap a job so only ONE instance runs it per interval (Redis SET NX EX lock).
    Without Redis the lock returns a 'local' sentinel → the job always runs (correct
    for dev / single instance). Idempotent syncs make the fail-open behavior safe."""

    async def runner(**kwargs):
        token = await try_acquire_lock(job_name, ttl)
        if token is None:
            log.info("%s: lock held by another instance — skipping this tick", job_name)
            return
        await fn(**kwargs)

    return runner


def start_scheduler(interval_minutes: int, leads_interval_hours: int = 4) -> None:
    global _scheduler
    if _scheduler is not None:
        return
    from ..services.inventory_sync import run_sync
    from ..services.leads_sync import run_leads_sync

    inv_min = max(1, interval_minutes)
    leads_hr = max(1, leads_interval_hours)
    # lock TTL slightly under the interval so the next tick can re-race after expiry
    inv_ttl = max(60, inv_min * 60 - 30)
    leads_ttl = max(60, leads_hr * 3600 - 60)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        locked_job("inventory_sync", run_sync, inv_ttl),
        "interval",
        minutes=inv_min,
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="inventory_sync",
    )
    # leads ingest is insert-only — adds new leads, never updates or deletes
    _scheduler.add_job(
        locked_job("leads_sync", run_leads_sync, leads_ttl),
        "interval",
        hours=leads_hr,
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="leads_sync",
    )
    _scheduler.start()
    log.info("inventory sync every %d min; leads ingest every %d h", inv_min, leads_hr)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
