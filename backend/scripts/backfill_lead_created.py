"""Give every existing lead a "{Lead} created on {date} via {source}" activity entry.

    uv run python scripts/backfill_lead_created.py            # dry run
    uv run python scripts/backfill_lead_created.py --apply    # write

Dry run by default. This writes to the live database — `backend/.env` points at
production and there is no staging — so it prints which database it is about to touch
before it touches anything.

Date is the lead's own `created_at` and source is its current `source`. The entry is
written with that historical timestamp, not today's, so it sorts into the right place in
each lead's history instead of bunching every lead at the top as if created this morning.

Safe to re-run: a lead that already has a `lead_created` entry is skipped. The WhatsApp
create endpoints have always logged one, and a second run after new leads have arrived
fills in only those.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import dispose_engines, neon_engine  # noqa: E402
from app.services.activity import (  # noqa: E402
    BACKFILL_LEAD_CREATED,
    COUNT_MISSING_LEAD_CREATED,
)

SAMPLE = text("""
    SELECT l.name, l.source, (l.created_at AT TIME ZONE 'Asia/Kolkata')::date AS created_ist
      FROM leads l
     WHERE NOT EXISTS (SELECT 1 FROM activity_log a
                        WHERE a.action = 'lead_created' AND a.entity_type = 'lead'
                          AND a.entity_id = l.id::text)
     ORDER BY l.created_at
     LIMIT 5
""")


async def main(apply: bool) -> int:
    engine = neon_engine()
    if engine is None:
        print("DATABASE_URL is not set — nothing to do", file=sys.stderr)
        return 1
    try:
        async with engine.connect() as conn:
            db = (await conn.execute(text("SELECT current_database()"))).scalar()
            missing = (await conn.execute(COUNT_MISSING_LEAD_CREATED)).scalar()
            sample = (await conn.execute(SAMPLE)).mappings().all()
            by_source = (await conn.execute(text(
                "SELECT source, count(*) FROM leads l WHERE NOT EXISTS ("
                "  SELECT 1 FROM activity_log a WHERE a.action = 'lead_created'"
                "  AND a.entity_type = 'lead' AND a.entity_id = l.id::text)"
                " GROUP BY 1 ORDER BY 2 DESC"))).all()

        print(f"database : {db}  ({urlparse(get_settings().neon_url).hostname})")
        print(f"leads without a 'created' entry: {missing}")
        for source, n in by_source:
            print(f"    {source:<14} {n}")
        if sample:
            print("oldest few, as they will read:")
            for r in sample:
                print(f"    {r['name'] or 'Lead'} created on {r['created_ist']} via {r['source']}")

        if not missing:
            print("nothing to backfill.")
            return 0
        if not apply:
            print("\ndry run — re-run with --apply to write these entries.")
            return 0

        async with engine.begin() as conn:
            written = (await conn.execute(BACKFILL_LEAD_CREATED)).rowcount
            left = (await conn.execute(COUNT_MISSING_LEAD_CREATED)).scalar()
        print(f"\nwrote {written} entries · still missing: {left}")
        return 0
    finally:
        await dispose_engines()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the entries (default: dry run)")
    raise SystemExit(asyncio.run(main(parser.parse_args().apply)))
