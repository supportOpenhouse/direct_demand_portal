-- Park the four test leads one per worklist, so every page has something in it.
--
--   Saranch Test      85955 94789 → New Leads
--   Rahul Test        70119 59640 → Call Not Received
--   TEST Listing Lead 93104 30779 → Follow Up      (currently RNR)
--   TEST Meta Lead    93103 08584 → Qualified
--
-- Each stage carries companion fields the app sets alongside it (miss_count,
-- ever_connected, follow_up_at, …). Setting `stage` alone would put a lead on the
-- right page in a state the UI never produces — e.g. a Follow-up row with no
-- callback time, or a Call-Not-Received row already marked as connected — so the
-- whole shape is written here, matching routers/leads.py.
--
-- Phones are matched on their last 10 digits, so stored formatting doesn't matter.
-- Re-runnable: it always writes the same end state.

BEGIN;

WITH target(digits, stage) AS (
    VALUES ('8595594789', 'new'),
           ('7011959640', 'call_not_received'),
           ('9310430779', 'follow_up'),
           ('9310308584', 'qualified')
)
UPDATE leads l SET
    stage = t.stage,

    -- Call-Not-Received means "rang, never reached": one miss on the counter, and
    -- ever_connected stays false — that flag is what routes the next missed call to
    -- CNR rather than Follow-up, and drives the RNR cutoff at 10.
    miss_count      = CASE WHEN t.stage = 'call_not_received' THEN 1 ELSE 0 END,
    ever_connected  = (t.stage IN ('follow_up', 'qualified')),

    -- Both worklists are due-time ordered, so a row without one sorts last and looks
    -- broken. CNR gets a retry in 2h; Follow-up a callback tomorrow morning.
    follow_up_at    = CASE t.stage
                          WHEN 'call_not_received' THEN now() + interval '2 hours'
                          WHEN 'follow_up'         THEN date_trunc('day', now()) + interval '1 day 10 hours'
                      END,
    follow_up_since = CASE WHEN t.stage IN ('call_not_received', 'follow_up')
                           THEN COALESCE(l.follow_up_since, now()) END,

    -- Qualified rows are the ones that went through the Q1–Q6 form.
    confirmed       = (t.stage = 'qualified'),
    qualified_at    = CASE WHEN t.stage = 'qualified' THEN COALESCE(l.qualified_at, now()) END,

    -- TEST Listing Lead is on 'rnr' today; its rejection trail has to go with it,
    -- otherwise the Rejected page keeps showing a reason for a lead that left.
    reject_reason = NULL,
    reject_notes  = NULL,
    rejected_at   = NULL,

    last_no_timestamp = NULL,  -- clears the 2-hour "No" cooldown, so you can click straight away
    updated_at        = now()
FROM target t
WHERE right(regexp_replace(l.phone, '\D', '', 'g'), 10) = t.digits
RETURNING l.name, l.phone, l.stage, l.miss_count, l.ever_connected, l.follow_up_at;

-- Expect 4 rows back. Fewer means a number didn't match — check it before COMMIT.
COMMIT;
