"""The recurring jobs, for a Render Cron Job.

    cd backend
    uv run python scripts/20_cron_tasks.py                 # all three
    uv run python scripts/20_cron_tasks.py --task leads    # just one
    uv run python scripts/20_cron_tasks.py --dry-run       # say what would run, do nothing

Tasks, in the order they run:

  visits    Re-pull the visits that aren't finished yet (app_visit_data). Completed and
            cancelled ones are skipped — Core never changes them again, so re-fetching
            them every ten minutes is thousands of requests to learn nothing.
            ⚠️ This REFRESHES; it does not DISCOVER. A visit we hold no row for is only
            picked up by the full walk, scripts/17_fill_all_visits.py. Schedule that one
            daily if new Openhouse visits should appear on their own.

  whatsapp  Give every unowned, non-rejected WhatsApp conversation an owner.
            ⚠️ This REVERSES a deliberate decision from 29 Aug: inbound conversations were
            made unassigned-until-someone-takes-one, because an unowned thread is visible
            to admins and a wrongly-owned one is invisible to everyone else. On a cron,
            ownership is automatic again. Rejected contacts are still never handed out.

  leads     Round-robin an owner onto every lead that arrived without one. The SAME sweep
            the in-app hourly job runs, so the two can't balance differently.
            ⚠️ The in-app job still exists. Two schedulers doing this is not harmful —
            each pick re-checks `assigned_to IS NULL`, so the loser of a race assigns
            nothing — but set LEAD_ASSIGN_INTERVAL_MINUTES high, or drop the in-app job,
            rather than leaving both on a tight interval.

Exit code is non-zero if any task failed, so Render marks the run failed instead of
reporting a green tick over a job that did nothing. One task failing does not stop the
others — they are independent, and a Core outage shouldn't hold up lead assignment.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import dispose_engines, neon_engine  # noqa: E402

TASKS = ("visits", "whatsapp", "leads")


async def task_visits() -> dict:
    from app.services.app_visit_data import run_upcoming_visits_refresh

    return await run_upcoming_visits_refresh(trigger="cron")


async def task_whatsapp() -> dict:
    from app.services.wa_assign import backfill

    engine = neon_engine()
    async with engine.begin() as conn:
        return {"assigned": await backfill(conn)}


async def task_leads() -> dict:
    from app.services.lead_assign import run_assignment_sweep

    return await run_assignment_sweep(trigger="cron")


RUNNERS = {"visits": task_visits, "whatsapp": task_whatsapp, "leads": task_leads}


async def main(which: list[str], dry_run: bool) -> int:
    if neon_engine() is None:
        print("DATABASE_URL not configured", file=sys.stderr)
        return 1
    host = urlparse(get_settings().DATABASE_URL).hostname
    print(f"database : {host}")
    print(f"tasks    : {', '.join(which)}{'  (dry run — nothing runs)' if dry_run else ''}\n")
    if dry_run:
        return 0

    failed = 0
    try:
        for name in which:
            t0 = time.time()
            try:
                result = await RUNNERS[name]()
                print(f"  {name:<9} ok    {time.time() - t0:5.1f}s  {result}")
            except Exception as e:  # noqa: BLE001 — one task must not stop the others
                failed += 1
                print(f"  {name:<9} FAILED {time.time() - t0:5.1f}s  {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        await dispose_engines()
    print(f"\n{len(which) - failed}/{len(which)} ok")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", action="append", choices=TASKS,
                    help="run only this task (repeatable); default is all three")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.task or list(TASKS), a.dry_run)))
