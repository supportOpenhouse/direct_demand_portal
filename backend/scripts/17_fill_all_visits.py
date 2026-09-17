"""Pull EVERY visit on Openhouse into app_visit_data — from GET crm/all-visits/.

    cd backend
    uv run python scripts/17_fill_all_visits.py            # dry run: fetch + count, writes nothing
    uv run python scripts/17_fill_all_visits.py --apply    # write it

This touches the live database — `backend/.env` points at production and there is no
staging — so it prints which database it is on before anything else, and a dry run is
the default.

What --apply does, in order:
  1. Drops the foreign key app_visit_data.visit_id → crm_visits.visit_id, if it's still
     there. crm_visits only holds visits WE booked; every other Openhouse visit would
     violate it and roll back its whole insert batch. visit_id stays the primary key, so
     `JOIN crm_visits USING (visit_id)` still finds our own row for a visit we booked.
  2. Upserts one row per visit (insert new, refresh existing), 500 per transaction.

No repeats: offset paging can hand back the same visit twice if Core writes a new visit
mid-walk. Repeats are removed before writing — keeping the copy with the newest
updatedAt — and visit_id is the primary key, so the table can't hold one twice anyway.
The count dropped is printed.

Safe to re-run. A failed page request stops the run before anything is written.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import dispose_engines, neon_engine  # noqa: E402
from app.models import AppVisitData  # noqa: E402
from app.services.app_visit_data import run_all_visits_sync  # noqa: E402

# the FK's name is whatever Postgres generated when the table was created — look it up
# rather than guess, so this works however the table was made
FK_NAMES = text("""
    SELECT conname FROM pg_constraint
     WHERE conrelid = 'app_visit_data'::regclass AND contype = 'f'
""")

SUMMARY = text("""
    SELECT count(*)                                            AS rows,
           count(DISTINCT visit_id)                            AS distinct_visit_ids,
           count(*) FILTER (WHERE c.visit_id IS NOT NULL)      AS booked_by_us,
           count(*) FILTER (WHERE c.visit_id IS NULL)          AS not_booked_by_us
      FROM app_visit_data a
      LEFT JOIN crm_visits c USING (visit_id)
""")


async def main(apply: bool) -> None:
    engine = neon_engine()
    if engine is None:
        sys.exit("DATABASE_URL not configured")
    host = urlparse(get_settings().DATABASE_URL).hostname
    base = get_settings().CRM_BOOKING_API_BASE_URL
    try:
        async with engine.begin() as conn:
            db = (await conn.execute(text("SELECT current_database()"))).scalar()
            print(f"database : {db} @ {host}")
            print(f"core api : {base}crm/all-visits/")
            print(f"mode     : {'APPLY — will write' if apply else 'dry run — writes nothing'}\n")
            await conn.run_sync(lambda c: AppVisitData.__table__.create(c, checkfirst=True))
            before = dict((await conn.execute(SUMMARY)).mappings().one())
            fks = [r[0] for r in await conn.execute(FK_NAMES)]
        print("before   :", before)
        print("fk to crm_visits:", fks or "none")

        if apply and fks:
            async with engine.begin() as conn:
                for name in fks:
                    await conn.execute(text(f'ALTER TABLE app_visit_data DROP CONSTRAINT "{name}"'))
            print("         → dropped", fks)

        t0 = time.time()
        print("\nfetching every visit from Openhouse…")
        result = await run_all_visits_sync(trigger="script", apply=apply)
        print(f"done in {time.time() - t0:.1f}s")
        for k in ("fetched", "repeats_dropped", "unique_visits", "new_rows", "updated_rows",
                  "booked_by_us", "not_booked_by_us"):
            print(f"  {k:<18} {result[k]}")

        if apply:
            async with engine.connect() as conn:
                after = dict((await conn.execute(SUMMARY)).mappings().one())
            print("\nafter    :", after)
            if after["rows"] != after["distinct_visit_ids"]:
                sys.exit("✗ repeated visit_id in app_visit_data — this should be impossible")
            print("✓ one row per visit, no repeats")
        else:
            print("\nnothing written. Re-run with --apply to write.")
    finally:
        await dispose_engines()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write to the database (default: dry run)")
    asyncio.run(main(ap.parse_args().apply))
