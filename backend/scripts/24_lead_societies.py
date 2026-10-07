"""Several societies per lead — leads.societies TEXT[] (spec 2026-10-07-lead-societies-design.md).

    cd backend
    uv run python scripts/24_lead_societies.py            # dry run: does EVERYTHING, prints, rolls back
    uv run python scripts/24_lead_societies.py --apply    # same, then commits

Run BEFORE deploying the code that reads `societies`. Old code never reads it, so this
order is safe. One transaction: column, sync trigger, backfill, past-merge append,
merge-trigger patch, verification. Any check failing rolls the whole thing back.
Takes an exclusive lock on `leads` for a few seconds — even the dry run.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import dispose_engines, neon_engine  # noqa: E402

ADD_COLUMN = "ALTER TABLE leads ADD COLUMN IF NOT EXISTS societies TEXT[] NOT NULL DEFAULT '{}'"

# Ingest writes `society`; the app writes `societies`. This keeps them in step:
#   insert with an empty list → {society}
#   societies written         → society = societies[1]   (societies wins if both are)
#   only society written      → {society}                (only pre-deploy code does this)
FILL_FUNCTION = """
CREATE OR REPLACE FUNCTION trg_leads_fill_societies()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF cardinality(NEW.societies) = 0 AND coalesce(btrim(NEW.society), '') <> '' THEN
            NEW.societies := ARRAY[btrim(NEW.society)];
        END IF;
    ELSIF NEW.societies IS DISTINCT FROM OLD.societies THEN
        NULL;  -- societies wins; society follows below
    ELSIF NEW.society IS DISTINCT FROM OLD.society THEN
        NEW.societies := CASE WHEN coalesce(btrim(NEW.society), '') = '' THEN '{}'::text[]
                              ELSE ARRAY[btrim(NEW.society)] END;
    END IF;
    NEW.society := NEW.societies[1];
    RETURN NEW;
END $$
"""
DROP_FILL_TRIGGER = "DROP TRIGGER IF EXISTS leads_fill_societies ON leads"
# Named to sort BEFORE leads_merge_source: same-event triggers fire alphabetically, and
# the merge trigger reads NEW.societies.
FILL_TRIGGER = """
CREATE TRIGGER leads_fill_societies
BEFORE INSERT OR UPDATE OF society, societies ON leads
FOR EACH ROW EXECUTE FUNCTION trg_leads_fill_societies()
"""

# What every lead held before this script — VERIFY checks against THIS, not against the
# society column the trigger rewrites.
SNAPSHOT = """
CREATE TEMP TABLE _before ON COMMIT DROP AS
SELECT id, btrim(society) AS s FROM leads WHERE coalesce(btrim(society), '') <> ''
"""

BACKFILL = """
UPDATE leads SET societies = ARRAY[btrim(society)]
 WHERE cardinality(societies) = 0 AND coalesce(btrim(society), '') <> ''
"""

# Each repeat arrival's society that the old merge trigger dropped, oldest first, one
# spelling per name, skipping any the lead already has. No activity rows: this restores
# data a merge lost; it is not work anyone did.
_ARRIVED = """
    SELECT a.entity_id AS lead_id,
           (array_agg(btrim(a.metadata->'lead'->>'society') ORDER BY a.created_at))[1] AS society,
           min(a.created_at) AS first_at
      FROM activity_log a
     WHERE a.entity_type = 'lead' AND a.action = 'lead_repeat'
       AND coalesce(btrim(a.metadata->'lead'->>'society'), '') <> ''
     GROUP BY a.entity_id, lower(btrim(a.metadata->'lead'->>'society'))
"""
APPEND_PAST_MERGES = f"""
WITH arrived AS ({_ARRIVED}),
missing AS (
    SELECT l.id, array_agg(x.society ORDER BY x.first_at) AS add
      FROM arrived x
      JOIN leads l ON l.id::text = x.lead_id
     WHERE NOT EXISTS (SELECT 1 FROM unnest(l.societies) AS e
                        WHERE lower(btrim(e)) = lower(x.society))
     GROUP BY l.id
)
UPDATE leads l SET societies = l.societies || m.add
  FROM missing m WHERE l.id = m.id
"""

LIVE_MERGE_BODY = "SELECT prosrc FROM pg_proc WHERE proname = 'trg_leads_merge_source' AND prokind = 'f'"
MERGE_ANCHOR = "merged_origin_keys = merged_origin_keys || NEW.origin_key,"
MERGE_APPEND = """
           -- the arriving societies join the list, case-insensitively (scripts/24)
           societies = societies || ARRAY(
               SELECT s FROM unnest(NEW.societies) AS s
                WHERE NOT EXISTS (SELECT 1 FROM unnest(leads.societies) AS e
                                   WHERE lower(btrim(e)) = lower(btrim(s)))),"""


def patched_merge_body(live: str) -> str | None:
    """The LIVE body with the append added — patched by anchor, like scripts/18, so a
    hand change elsewhere in the function survives. None = already applied."""
    if "unnest(NEW.societies)" in live:
        return None
    if live.count(MERGE_ANCHOR) != 1:
        raise SystemExit("trg_leads_merge_source no longer matches scripts/07 — patch it by hand")
    return live.replace(MERGE_ANCHOR, MERGE_ANCHOR + MERGE_APPEND)


def merge_function_sql(body: str) -> str:
    return ("CREATE OR REPLACE FUNCTION trg_leads_merge_source() RETURNS trigger "
            f"LANGUAGE plpgsql AS $merge${body}$merge$")


# All three must be 0. `lost`: a society a lead held before the script that is not in
# its list now. `merge_missing`: a past repeat arrival's society still absent.
# `out_of_step`: society ≠ societies[1].
VERIFY = f"""
WITH arrived AS ({_ARRIVED})
SELECT (SELECT count(*) FROM _before) AS before_with_society,
       (SELECT count(*) FROM leads WHERE cardinality(societies) > 0) AS after_with_societies,
       (SELECT count(*) FROM _before b JOIN leads l ON l.id = b.id
         WHERE NOT EXISTS (SELECT 1 FROM unnest(l.societies) AS e
                            WHERE lower(btrim(e)) = lower(b.s))) AS lost,
       (SELECT count(*) FROM arrived x JOIN leads l ON l.id::text = x.lead_id
         WHERE NOT EXISTS (SELECT 1 FROM unnest(l.societies) AS e
                            WHERE lower(btrim(e)) = lower(x.society))) AS merge_missing,
       (SELECT count(*) FROM leads WHERE society IS DISTINCT FROM societies[1]) AS out_of_step
"""

SAMPLE = """
SELECT name, society, societies FROM leads WHERE cardinality(societies) > 1
 ORDER BY cardinality(societies) DESC, name LIMIT 10
"""


async def main(apply: bool) -> None:
    async with neon_engine().connect() as conn:
        db = (await conn.exec_driver_sql("SELECT current_database()")).scalar()
        host = urlparse(get_settings().DATABASE_URL).hostname
        print(f"database: {db} @ {host} · {'APPLY' if apply else 'DRY RUN — everything runs, then rolls back'}")
        # that SELECT autobegan the ONE transaction everything below runs in
        try:
            await conn.exec_driver_sql(SNAPSHOT)
            await conn.exec_driver_sql(ADD_COLUMN)
            await conn.exec_driver_sql(FILL_FUNCTION)
            await conn.exec_driver_sql(DROP_FILL_TRIGGER)
            await conn.exec_driver_sql(FILL_TRIGGER)
            print("backfilled:", (await conn.exec_driver_sql(BACKFILL)).rowcount, "leads")
            print("past merges appended to:", (await conn.exec_driver_sql(APPEND_PAST_MERGES)).rowcount, "leads")
            live = (await conn.exec_driver_sql(LIVE_MERGE_BODY)).scalar()
            body = patched_merge_body(live)
            if body is None:
                print("merge trigger: already appends — unchanged")
            else:
                await conn.exec_driver_sql(merge_function_sql(body))
                print("merge trigger: now appends arriving societies")
            v = dict((await conn.exec_driver_sql(VERIFY)).mappings().one())
            print("verify:", v)
            for r in (await conn.exec_driver_sql(SAMPLE)).mappings():
                print("  ", r["name"], "|", r["society"], "|", r["societies"])
            if v["lost"] or v["merge_missing"] or v["out_of_step"]:
                raise SystemExit("verification FAILED — rolled back, nothing written")
        except BaseException:
            await conn.rollback()
            raise
        if apply:
            await conn.commit()
            print("committed")
        else:
            await conn.rollback()
            print("rolled back (dry run) — re-run with --apply to write")
    await dispose_engines()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    asyncio.run(main(p.parse_args().apply))
