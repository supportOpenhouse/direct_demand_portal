-- Visit planner: split the single `rm` field into two roles.
--
--   visits.rm  (today: labelled "RM accompanying", actually the lead's own RM)
--     ├── lead_rm          ← the RM who owns the lead
--     └── rm_accompanying  ← who actually goes on the visit; defaults to lead_rm,
--                            and is what gets sent as sales_manager_id when booking
--
-- ADDITIVE ONLY. `rm` is left in place and still populated, so this can be deployed
-- ahead of the code and rolled back by simply ignoring the new columns. Drop `rm`
-- in a later cleanup, once nothing reads it.
--
--   psql "$DATABASE_URL" -f backend/scripts/split_visit_rm.sql
--
-- Idempotent: the columns are guarded, and the back-fill only touches NULLs, so
-- re-running never overwrites a value someone has since changed by hand.

\echo '=== BEFORE ==='
SELECT count(*) AS plans, count(rm) AS with_rm FROM visits;

BEGIN;

ALTER TABLE visits ADD COLUMN IF NOT EXISTS lead_rm         TEXT;
ALTER TABLE visits ADD COLUMN IF NOT EXISTS rm_accompanying TEXT;

-- Both start from `rm`: the stored value IS the lead's RM, and the accompanying RM
-- defaults to that same person until someone picks a different one.
UPDATE visits SET lead_rm         = rm WHERE lead_rm         IS NULL AND rm IS NOT NULL;
UPDATE visits SET rm_accompanying = rm WHERE rm_accompanying IS NULL AND rm IS NOT NULL;

COMMIT;

\echo '=== AFTER ==='
SELECT count(*) AS plans,
       count(rm)              AS legacy_rm,
       count(lead_rm)         AS lead_rm,
       count(rm_accompanying) AS rm_accompanying
FROM visits;

\echo '=== should be empty: rows where the copy did not land ==='
SELECT id, lead_id, rm, lead_rm, rm_accompanying
FROM visits
WHERE rm IS NOT NULL AND (lead_rm IS NULL OR rm_accompanying IS NULL);
