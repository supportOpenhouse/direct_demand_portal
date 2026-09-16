-- Clear follow-ups the SYSTEM set, keep the ones a person set.
--
-- NOT RUN. Read step 1, decide on step 3, then run what you want.
--
-- The code no longer creates auto follow-ups (routers/leads.py: a missed call clears the
-- due time instead of scheduling +3h/+6h). This file is only about the rows already in
-- the table.
--
-- ⚠️ "No follow_up_set activity row" is NOT the test for an auto follow-up. The qualify
-- form writes follow_up_at and logs only stage_change, so 600 human-entered follow-ups
-- have no follow_up_set row and that test would delete every one of them.
--
-- The reliable marker is the missed-call path's own receipt: it recorded the exact time
-- it set in the call_missed activity row's metadata. A lead whose CURRENT follow_up_at
-- still equals that stamp has not been touched by a human since.
--
-- Measured on prod, 16 Sep — 3,106 leads hold a follow_up_at:
--      947  exactly match their last auto stamp      → step 3a, safe to clear
--      251  have a follow_up_set row (manual)        → keep
--      600  have a qualify form on file              → keep
--    1,439  none of the above                        → step 3b, YOUR CALL
--  (buckets overlap; the queries below apply keep-rules first.)
--
-- The 1,439 predate activity logging (it started 19 Aug) — nothing records who set them
-- or how, so they cannot be attributed either way. Clearing them is a judgement call
-- about stale data, not a fact about its origin.

-- 0. confirm prod
SELECT current_database(), inet_server_addr();

-- 1. the picture, by what we can actually prove about each row
WITH last_miss AS (
    SELECT DISTINCT ON (entity_id)
           entity_id, (metadata->>'follow_up_at')::timestamptz AS auto_fu
      FROM activity_log
     WHERE action = 'call_missed' AND entity_type = 'lead'
       AND metadata->>'follow_up_at' IS NOT NULL
     ORDER BY entity_id, created_at DESC
),
manual AS (SELECT DISTINCT entity_id FROM activity_log WHERE action = 'follow_up_set'),
qualified AS (SELECT DISTINCT lead_id::text AS entity_id FROM lead_confirmed_data)
SELECT CASE
         WHEN m.entity_id IS NOT NULL THEN 'keep — person set it'
         WHEN q.entity_id IS NOT NULL THEN 'keep — qualify form'
         WHEN date_trunc('second', l.follow_up_at) = date_trunc('second', lm.auto_fu)
              THEN 'clear — auto (step 3a)'
         ELSE 'unattributable (step 3b)'
       END AS bucket,
       count(*), min(l.follow_up_at) AS earliest, max(l.follow_up_at) AS latest
  FROM leads l
  LEFT JOIN last_miss lm ON lm.entity_id = l.id::text
  LEFT JOIN manual    m  ON m.entity_id  = l.id::text
  LEFT JOIN qualified q  ON q.entity_id  = l.id::text
 WHERE l.follow_up_at IS NOT NULL
 GROUP BY 1 ORDER BY 2 DESC;

-- 2. sanity: no lead about to be cleared has a human receipt
--    (must return 0 — if it doesn't, STOP and re-read step 1)
WITH last_miss AS (
    SELECT DISTINCT ON (entity_id)
           entity_id, (metadata->>'follow_up_at')::timestamptz AS auto_fu
      FROM activity_log
     WHERE action = 'call_missed' AND entity_type = 'lead'
       AND metadata->>'follow_up_at' IS NOT NULL
     ORDER BY entity_id, created_at DESC
)
SELECT count(*) AS must_be_zero
  FROM leads l
  JOIN last_miss lm ON lm.entity_id = l.id::text
 WHERE l.follow_up_at IS NOT NULL
   AND date_trunc('second', l.follow_up_at) = date_trunc('second', lm.auto_fu)
   AND (EXISTS (SELECT 1 FROM activity_log a
                 WHERE a.entity_id = l.id::text AND a.action = 'follow_up_set')
     OR EXISTS (SELECT 1 FROM lead_confirmed_data c WHERE c.lead_id = l.id));

-- 3a. clear the provably-auto ones (~947).
--     stage is NOT touched: stage writes are forward-only, and a lead in follow_up with
--     no due time is a lead that needs calling and has no appointment — which is exactly
--     what it always was. follow_up_since goes too; it only dated the tint that's gone.
/*
WITH last_miss AS (
    SELECT DISTINCT ON (entity_id)
           entity_id, (metadata->>'follow_up_at')::timestamptz AS auto_fu
      FROM activity_log
     WHERE action = 'call_missed' AND entity_type = 'lead'
       AND metadata->>'follow_up_at' IS NOT NULL
     ORDER BY entity_id, created_at DESC
)
UPDATE leads l
   SET follow_up_at = NULL, follow_up_since = NULL
  FROM last_miss lm
 WHERE lm.entity_id = l.id::text
   AND l.follow_up_at IS NOT NULL
   AND date_trunc('second', l.follow_up_at) = date_trunc('second', lm.auto_fu)
   AND NOT EXISTS (SELECT 1 FROM activity_log a
                    WHERE a.entity_id = l.id::text AND a.action = 'follow_up_set')
   AND NOT EXISTS (SELECT 1 FROM lead_confirmed_data c WHERE c.lead_id = l.id);
*/

-- 3b. the 1,439 unattributable ones. ONLY run this if you've decided that a follow-up
--     nobody can account for should not sit on the Follow-up page. It is not reversible
--     — there is no record of these times anywhere else.
/*
UPDATE leads l
   SET follow_up_at = NULL, follow_up_since = NULL
 WHERE l.follow_up_at IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM activity_log a
                    WHERE a.entity_id = l.id::text AND a.action = 'follow_up_set')
   AND NOT EXISTS (SELECT 1 FROM lead_confirmed_data c WHERE c.lead_id = l.id);
*/

-- 4. after: what's left should be the 251 manual + 600 qualify-form
SELECT count(*) AS leads_with_followup,
       count(*) FILTER (WHERE stage = 'follow_up') AS in_followup_stage
  FROM leads WHERE follow_up_at IS NOT NULL;
