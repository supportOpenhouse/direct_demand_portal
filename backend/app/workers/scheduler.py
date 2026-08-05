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


# Leads ingest fires at fixed IST wall-clock times (Asia/Kolkata — no DST, so these
# are stable). Change here to re-time the twice-daily lead sync.
LEADS_SYNC_TIMES_IST = [(11, 30), (14, 0)]  # 11:30 AM and 2:00 PM IST


def start_scheduler(interval_minutes: int, leads_interval_hours: int = 4) -> None:
    global _scheduler
    if _scheduler is not None:
        return
    from apscheduler.triggers.combining import OrTrigger
    from apscheduler.triggers.cron import CronTrigger

    from ..config import get_settings
    from ..services.inventory_sync import run_sync
    from ..services.leads_sync import run_leads_sync
    from ..services.visits_sync import run_visits_sync

    inv_min = max(1, interval_minutes)
    # lock TTL slightly under the interval so the next tick can re-race after expiry
    inv_ttl = max(60, inv_min * 60 - 30)
    # fixed 15-min lock for leads: covers a sync run, well under the gap between fire times
    leads_ttl = 900

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
    # leads ingest is insert-only — adds new leads, never updates or deletes.
    # Fires at the fixed IST clock times above (one job, multiple triggers).
    leads_trigger = OrTrigger([
        CronTrigger(hour=h, minute=m, timezone="Asia/Kolkata") for h, m in LEADS_SYNC_TIMES_IST
    ])
    _scheduler.add_job(
        locked_job("leads_sync", run_leads_sync, leads_ttl),
        leads_trigger,
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="leads_sync",
    )
    # visit status (upcoming → completed/cancelled) from the ops sheet
    vis_min = max(5, get_settings().VISITS_SYNC_INTERVAL_MINUTES)
    _scheduler.add_job(
        locked_job("visits_sync", run_visits_sync, max(60, vis_min * 60 - 30)),
        "interval",
        minutes=vis_min,
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="visits_sync",
    )
    # Bonvoice call log. The webhook is the primary path; this catches dropped
    # callbacks and calls dialled straight from a handset. Skips itself when Bonvoice
    # isn't configured, so it's harmless on an unconfigured deploy.
    from ..routers.bonvoice import run_call_log_sync  # local: avoids a router↔worker import cycle

    call_min = max(1, get_settings().BONVOICE_SYNC_INTERVAL_MINUTES)
    _scheduler.add_job(
        locked_job("bonvoice_call_sync", run_call_log_sync, max(60, call_min * 60 - 30)),
        "interval",
        minutes=call_min,
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="bonvoice_call_sync",
    )
    _scheduler.start()
    times = ", ".join(f"{h:02d}:{m:02d}" for h, m in LEADS_SYNC_TIMES_IST)
    log.info("inventory sync every %d min; leads ingest at %s IST; visit status every %d min; "
             "bonvoice call log every %d min", inv_min, times, vis_min, call_min)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
