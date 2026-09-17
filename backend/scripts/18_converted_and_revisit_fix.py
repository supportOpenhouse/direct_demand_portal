"""Two data fixes, in one pass:

  1. Stage `won` → `converted` — the name the team actually uses.
  2. `revisit_scheduled` only where the lead really has TWO visits to the SAME property.
     Anything else that was marked a revisit goes back to `visit_scheduled`.

    cd backend
    uv run python scripts/18_converted_and_revisit_fix.py            # dry run, writes nothing
    uv run python scripts/18_converted_and_revisit_fix.py --apply    # write it

This touches the live database — `backend/.env` points at production and there is no
staging — so it prints which database it is on first, and a dry run is the default.

⚠️ Run this together with the deploy that renames the stage in code. In between, one side
calls it `won` and the other `converted`, and the Converted page reads empty for whichever
is behind.

⚠️ It also rewrites any DATABASE FUNCTION whose body mentions 'won' — `trg_lead_repeat_count`
(scripts/07_lead_sources.sql) lists the terminal stages inline, so leaving it alone would
make a repeat arrival reset a CONVERTED lead back to New. The body is read from
pg_get_functiondef and re-created with the word swapped, so whatever is actually deployed
gets patched rather than whatever this repo thinks is deployed.

The revisit fix moves stages in BOTH directions and is deliberately NOT logged to
activity_log: it corrects a rule that was wrong, it is not work an RM did, and a
stage_change row per lead would land in the Reports "Revisit" metric.
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

BEFORE = text("SELECT stage, count(*) FROM leads GROUP BY 1 ORDER BY 2 DESC")

# a lead is a revisit only if some property has 2+ visits that actually happened or are
# still on — cancelled ones never happened, so they can't make a revisit
REPEAT_HOME = """
    EXISTS (SELECT 1 FROM crm_visits v
             WHERE v.lead_id = l.id AND v.home_id IS NOT NULL AND v.status <> 'cancelled'
             GROUP BY v.home_id HAVING count(*) >= 2)
"""
PLAN = text(f"""
    SELECT l.stage AS now,
           CASE WHEN {REPEAT_HOME} THEN 'revisit_scheduled' ELSE 'visit_scheduled' END AS target,
           count(*)
      FROM leads l
     WHERE l.stage IN ('visit_scheduled','revisit_scheduled')
     GROUP BY 1, 2 ORDER BY 3 DESC
""")
FIX_STAGES = text(f"""
    UPDATE leads l
       SET stage = CASE WHEN {REPEAT_HOME} THEN 'revisit_scheduled' ELSE 'visit_scheduled' END
     WHERE l.stage IN ('visit_scheduled','revisit_scheduled')
       AND l.stage IS DISTINCT FROM
           (CASE WHEN {REPEAT_HOME} THEN 'revisit_scheduled' ELSE 'visit_scheduled' END)
""")
RENAME = text("UPDATE leads SET stage = 'converted' WHERE stage = 'won'")
# activity_log keeps history: rows that RECORDED the move to 'won' should read the same
# name as the stage does now, or the lead history shows a stage that no longer exists
RENAME_LOG = text("""
    UPDATE activity_log SET after_value = 'converted'
     WHERE action = 'stage_change' AND after_value = 'won'
""")
RENAME_LOG_BEFORE = text("""
    UPDATE activity_log SET before_value = 'converted'
     WHERE action = 'stage_change' AND before_value = 'won'
""")
# ⚠️ Two steps on purpose. pg_get_functiondef() THROWS on an aggregate ("array_agg is an
# aggregate function"), and a WHERE that calls it is evaluated across every function in the
# schema before any filter narrows it — so the whole query dies on somebody else's
# aggregate. Filter on prosrc, a plain column, and keep prokind = 'f' (a normal function);
# only then ask for each definition, one oid at a time.
FUNC_OIDS = text("""
    SELECT p.oid, p.oid::regprocedure::text AS sig
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public' AND p.prokind = 'f' AND p.prosrc LIKE '%''won''%'
     ORDER BY 2
""")
FUNC_DEF = text("SELECT pg_get_functiondef(:oid)")


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

            print("stages now:")
            for stage, n in (await conn.execute(BEFORE)).all():
                print(f"  {stage:<20} {n:>6}")

            print("\nvisit stages — what the 2-visits-same-home rule says:")
            for now, target, n in (await conn.execute(PLAN)).all():
                mark = "  (no change)" if now == target else "  → CHANGES"
                print(f"  {now:<20} → {target:<20} {n:>5}{mark}")

            funcs = []
            for oid, sig in (await conn.execute(FUNC_OIDS)).all():
                definition = (await conn.execute(FUNC_DEF, {"oid": oid})).scalar()
                funcs.append((sig, definition))
            print(f"\ndatabase functions mentioning 'won': {[f[0] for f in funcs] or 'none'}")

        if not apply:
            print("\nnothing written. Re-run with --apply to write.")
            return

        async with engine.begin() as conn:
            # functions first: a lead renamed to 'converted' while the trigger still
            # tests for 'won' is exactly the window this ordering closes
            for sig, definition in funcs:
                await conn.execute(text(definition.replace("'won'", "'converted'")))
                print(f"  rebuilt {sig}")
            renamed = (await conn.execute(RENAME)).rowcount
            logs = (await conn.execute(RENAME_LOG)).rowcount
            logs += (await conn.execute(RENAME_LOG_BEFORE)).rowcount
            moved = (await conn.execute(FIX_STAGES)).rowcount
        print(f"\n  leads won → converted        {renamed}")
        print(f"  activity_log rows renamed    {logs}")
        print(f"  visit/revisit stages fixed   {moved}")

        async with engine.connect() as conn:
            print("\nstages after:")
            for stage, n in (await conn.execute(BEFORE)).all():
                print(f"  {stage:<20} {n:>6}")
            left = (await conn.execute(text("SELECT count(*) FROM leads WHERE stage = 'won'"))).scalar()
            bad = (await conn.execute(text(f"""
                SELECT count(*) FROM leads l WHERE l.stage = 'revisit_scheduled' AND NOT {REPEAT_HOME}
            """))).scalar()
        if left or bad:
            sys.exit(f"✗ {left} leads still 'won', {bad} revisits without a repeated property")
        print("\n✓ no 'won' left; every revisit_scheduled lead has 2+ visits to one property")
    finally:
        await dispose_engines()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write to the database (default: dry run)")
    asyncio.run(main(ap.parse_args().apply))
