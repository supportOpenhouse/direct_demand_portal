-- Lead stage migration — make `stage` authoritative for page routing.
-- Spec: docs/superpowers/specs/2026-07-29-lead-stage-model-design.md
--
-- The app applies these same statements at startup (app/migrations.py). This script is
-- for running by hand against Neon, with a backup and before/after counts.
--
--   psql "$DATABASE_URL" -f backend/scripts/migrate_stages.sql
--
-- Idempotent: after one run no row matches any WHERE, so re-running changes nothing.

\echo '=== BEFORE ==='
SELECT stage,
       count(*) FILTER (WHERE follow_up_at IS NOT NULL AND NOT ever_connected) AS to_cnr,
       count(*) FILTER (WHERE follow_up_at IS NOT NULL AND ever_connected)     AS to_followup,
       count(*)                                                                AS total
FROM leads GROUP BY stage ORDER BY total DESC;

BEGIN;

-- Reversible escape hatch: the migration overwrites `stage` with no record of the old
-- value. Keep this table until the new model has been live for a while.
--   restore:  UPDATE leads l SET stage = b.stage
--             FROM leads_stage_backup b WHERE b.id = l.id;
CREATE TABLE IF NOT EXISTS leads_stage_backup AS SELECT id, stage FROM leads;

-- 1. contacted + visit_planned are the qualified leads (150 + 9 = 159, matching the
--    dashboard's qualified count exactly).
UPDATE leads SET stage = 'qualified' WHERE stage IN ('contacted', 'visit_planned');

-- 2. new-stage leads with an open callback, split on whether we ever reached them.
--    These sit in Follow-up today; left alone they would wrongly return to New.
UPDATE leads SET stage = 'call_not_received'
 WHERE stage = 'new' AND follow_up_at IS NOT NULL AND NOT ever_connected;

UPDATE leads SET stage = 'follow_up'
 WHERE stage = 'new' AND follow_up_at IS NOT NULL AND ever_connected;

-- 3. stages referenced in code but holding zero rows
UPDATE leads SET stage = 'rejected' WHERE stage IN ('lost', 'future_prospect', 'timepass');

COMMIT;

\echo '=== AFTER ==='
SELECT stage, count(*) AS total FROM leads GROUP BY stage ORDER BY total DESC;

\echo '=== ORPHAN CHECK (must be empty) ==='
SELECT stage, count(*) FROM leads
WHERE stage NOT IN ('new','call_not_received','follow_up','qualified',
                    'visit_scheduled','won','rejected','rnr')
GROUP BY stage;
