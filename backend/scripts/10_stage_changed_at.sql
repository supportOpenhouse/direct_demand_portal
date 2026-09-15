-- leads.stage_changed_at — when the lead entered its CURRENT stage. Run top to bottom on
-- prod; idempotent.
--
-- There was no such column: only three stages had their own timestamp (qualified_at,
-- rejected_at, follow_up_since), and activity_log's stage_change rows only start on
-- 19 Aug. It drives the NEW badge for a lead moved back into `new` today — a repeat
-- arrival reset to New otherwise looks like an old lead, because received_at never
-- changes.
--
-- A trigger, not app code: stage is written by a dozen app paths AND by the
-- activity_log_lead_repeat trigger (the repeat reset), which never runs Python.

-- 0. confirm prod
SELECT current_database(), inet_server_addr();

-- 1. column (no default: an ALTER … DEFAULT now() would stamp every existing lead with
--    today, and every lead in New would show NEW)
ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_changed_at TIMESTAMPTZ;

-- 2. data: the latest logged move INTO the current stage; a lead still in `new` with no
--    such move has been there since it was created. Anything else we can't know
--    (moved before logging began) stays NULL rather than getting a made-up date.
UPDATE leads l
   SET stage_changed_at = coalesce(
         (SELECT max(a.created_at) FROM activity_log a
           WHERE a.action = 'stage_change' AND a.entity_type = 'lead'
             AND a.entity_id = l.id::text AND a.after_value = l.stage),
         CASE WHEN l.stage = 'new' THEN l.created_at END)
 WHERE l.stage_changed_at IS NULL;

-- 3. keep it current. INSERT stamps arrival; UPDATE stamps only a REAL change (a SET
--    stage = <same stage>, which forward-only CASEs do constantly, is not a move).
--    Fires after leads_merge_source (triggers of one timing run in name order), so a
--    merged arrival — insert cancelled — never reaches it.
CREATE OR REPLACE FUNCTION trg_stage_changed_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.stage_changed_at := coalesce(NEW.stage_changed_at, now());
    ELSIF NEW.stage IS DISTINCT FROM OLD.stage THEN
        NEW.stage_changed_at := now();
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS leads_stage_changed_at ON leads;
CREATE TRIGGER leads_stage_changed_at
BEFORE INSERT OR UPDATE OF stage ON leads
FOR EACH ROW
EXECUTE FUNCTION trg_stage_changed_at();

-- 4. check
SELECT stage, count(*) AS leads, count(stage_changed_at) AS with_timestamp,
       count(*) FILTER (WHERE (stage_changed_at AT TIME ZONE 'Asia/Kolkata')::date
                              = (now() AT TIME ZONE 'Asia/Kolkata')::date) AS moved_today
  FROM leads GROUP BY stage ORDER BY leads DESC;
