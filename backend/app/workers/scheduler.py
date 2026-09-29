import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

log = logging.getLogger("scheduler")
_scheduler: AsyncIOScheduler | None = None
# ponytail: no cross-instance lock. The cron runs only where RUN_SCHEDULER is on, and
# that is exactly one process; max_instances=1 stops a slow run overlapping itself.
# Scale to >1 scheduler process and every job runs once per process — add a
# pg_try_advisory_lock around each job then (the syncs are idempotent meanwhile).


def start_scheduler(interval_minutes: int) -> None:
    global _scheduler
    if _scheduler is not None:
        return
    from ..config import get_settings
    from ..services.inventory_sync import run_sync
    from ..services.leads_sync import run_leads_sync
    from ..services.visits_sync import run_visits_sync

    inv_min = max(1, interval_minutes)
    # near-real-time leads poll (default 2 min)
    leads_min = max(1, get_settings().LEADS_SYNC_INTERVAL_MINUTES)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_sync,
        "interval",
        minutes=inv_min,
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="inventory_sync",
    )
    # leads ingest is insert-only — adds new leads, never updates or deletes — so polling
    # frequently is safe; it just no-ops when the sheet has nothing new.
    _scheduler.add_job(
        run_leads_sync,
        "interval",
        minutes=leads_min,
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="leads_sync",
    )
    # visit status (upcoming → completed/cancelled) from the ops sheet
    vis_min = max(5, get_settings().VISITS_SYNC_INTERVAL_MINUTES)
    _scheduler.add_job(
        run_visits_sync,
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
        run_call_log_sync,
        "interval",
        minutes=call_min,
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="bonvoice_call_sync",
    )
    # Round-robin owner for every lead that arrived without one. A sweep rather than
    # inline at ingest, because the Apps Script INSERTs into `leads` directly over
    # Neon's HTTP endpoint and never runs any Python — reading the table catches it.
    from ..services.lead_assign import run_assignment_sweep

    assign_min = max(1, get_settings().LEAD_ASSIGN_INTERVAL_MINUTES)
    _scheduler.add_job(
        run_assignment_sweep,
        "interval",
        minutes=assign_min,
        kwargs={"trigger": "scheduler"},
        coalesce=True,
        max_instances=1,
        id="lead_assign",
    )
    _scheduler.start()
    log.info("inventory sync every %d min; leads ingest every %d min; visit status every %d min; "
             "bonvoice call log every %d min; lead assignment every %d min",
             inv_min, leads_min, vis_min, call_min, assign_min)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
