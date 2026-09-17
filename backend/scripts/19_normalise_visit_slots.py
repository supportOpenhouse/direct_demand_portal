"""One spelling for every slot already stored in crm_visits.

    cd backend
    uv run python scripts/19_normalise_visit_slots.py            # dry run, writes nothing
    uv run python scripts/19_normalise_visit_slots.py --apply    # write it

New bookings are canonical since the API started normalising, but rows written by older
builds still carry "3-5 PM". Core compares selected_time as a STRING, so the two spellings
are two different slots to it — which is what defeats its own duplicate-visit check.

Values are mapped with `canonical_slot`, the SAME function the API uses, so the table can't
end up holding a spelling the code would reject. Anything it doesn't recognise is REPORTED
and left alone — a slot nobody can parse is a fact about the data, not something to guess at.

⚠️ Only `crm_visits` (ours) is touched. `app_visit_data` is Core's verbatim record of what
Core returned; rewriting it would make it a record of what we wish Core had said.
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
from app.services.crm_booking import canonical_slot  # noqa: E402

DISTINCT = text("""
    SELECT selected_time AS raw, count(*) AS n
      FROM crm_visits WHERE selected_time IS NOT NULL
     GROUP BY 1 ORDER BY 2 DESC
""")
FIX = text("UPDATE crm_visits SET selected_time = :to WHERE selected_time = :frm")


async def main(apply: bool) -> None:
    engine = neon_engine()
    if engine is None:
        sys.exit("DATABASE_URL not configured")
    host = urlparse(get_settings().DATABASE_URL).hostname
    try:
        async with engine.connect() as conn:
            db = (await conn.execute(text("SELECT current_database()"))).scalar()
            print(f"database : {db} @ {host}")
            print(f"mode     : {'APPLY — will write' if apply else 'dry run — writes nothing'}\n")
            rows = (await conn.execute(DISTINCT)).all()

        changes, already, unknown = [], [], []
        for raw, n in rows:
            good = canonical_slot(raw)
            if good is None:
                unknown.append((raw, n))
            elif good == raw:
                already.append((raw, n))
            else:
                changes.append((raw, good, n))

        print(f"{'stored value':<20} {'count':>6}  →")
        for raw, good, n in changes:
            print(f"  {raw!r:<18} {n:>6}  → {good!r}")
        for raw, n in already:
            print(f"  {raw!r:<18} {n:>6}    (already canonical)")
        for raw, n in unknown:
            print(f"  {raw!r:<18} {n:>6}    ⚠ not a known slot — LEFT ALONE")

        total = sum(n for _, _, n in changes)
        print(f"\nrows to change: {total}   left alone: {sum(n for _, n in already) + sum(n for _, n in unknown)}")
        if unknown:
            print("⚠ unrecognised values stay as they are; decide on them by hand.")

        if not apply:
            print("\nnothing written. Re-run with --apply to write.")
            return
        if not changes:
            print("\nnothing to do.")
            return

        async with engine.begin() as conn:
            done = 0
            for raw, good, _ in changes:
                done += (await conn.execute(FIX, {"frm": raw, "to": good})).rowcount
        print(f"\nupdated {done} rows")

        async with engine.connect() as conn:
            after = (await conn.execute(DISTINCT)).all()
        bad = [(r, n) for r, n in after if canonical_slot(r) != r and canonical_slot(r) is not None]
        print("\nafter:")
        for raw, n in after:
            print(f"  {raw!r:<18} {n:>6}")
        if bad:
            sys.exit(f"✗ still non-canonical: {bad}")
        print("\n✓ every recognised slot is stored one way")
    finally:
        await dispose_engines()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write to the database (default: dry run)")
    asyncio.run(main(ap.parse_args().apply))
