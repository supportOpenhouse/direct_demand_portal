-- Multi-source leads + arrival count. Run top to bottom on prod; every statement is
-- idempotent. Builds on count_leads_repeat.sql (already applied 14 Sep).
--
-- A buyer is ONE lead per phone (last 10 digits) from now on:
--   * a new source for an existing phone does NOT create a lead. The BEFORE INSERT
--     trigger on leads adds the source to `sources`, remembers the origin_key in
--     `merged_origin_keys` and logs `lead_repeat` instead.
--   * a repeat Meta form (same source) is logged by the webhook as
--     meta_form_submitted with new_lead=false — unchanged.
--   * both kinds of activity row fire the activity_log trigger, which recounts
--     count_leads_repeat and moves the lead to 'new' unless it is at
--     visit_scheduled / revisit_scheduled / won.
-- Existing duplicate leads (65 phones) are NOT merged — forward only.

-- 0. confirm prod
SELECT current_database(), inet_server_addr();

-- 1. columns
ALTER TABLE leads ADD COLUMN IF NOT EXISTS sources TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS merged_origin_keys TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS count_leads_repeat INTEGER NOT NULL DEFAULT 0;

-- 2. indexes the trigger reads on every novel insert
CREATE INDEX IF NOT EXISTS ix_leads_phone10 ON leads (right(regexp_replace(phone, '\D', '', 'g'), 10));
CREATE INDEX IF NOT EXISTS ix_leads_merged_origin_keys ON leads USING gin (merged_origin_keys);

-- 3. data: every existing lead has exactly its own source
UPDATE leads SET sources = ARRAY[source] WHERE sources = '{}';

-- 4. arrivals beyond the first, from activity_log.
--    `merged` meta_form_submitted rows are excluded: that delivery was a new SOURCE and
--    is already counted by the lead_repeat row the leads trigger wrote for it.
CREATE OR REPLACE FUNCTION lead_repeat_count(p_lead_id uuid)
RETURNS integer LANGUAGE sql STABLE AS $$
    SELECT count(*)::int
      FROM activity_log a
     WHERE a.entity_type = 'lead'
       AND a.entity_id   = p_lead_id::text
       AND (a.action = 'lead_repeat'
            OR (a.action = 'meta_form_submitted'
                AND a.metadata->>'new_lead' = 'false'
                AND coalesce(a.metadata->>'merged', 'false') <> 'true'))
$$;

-- 5. on a repeat arrival: recount, and back to 'new' unless visit/revisit/won
CREATE OR REPLACE FUNCTION trg_lead_repeat_count()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_before text;
BEGIN
    SELECT stage INTO v_before FROM leads WHERE id = NEW.entity_id::uuid;
    IF v_before IS NULL THEN
        RETURN NULL;
    END IF;

    -- every SET expression reads the OLD row, so `stage` below is the stage before
    UPDATE leads
       SET count_leads_repeat = lead_repeat_count(id),
           stage        = CASE WHEN stage IN ('new','visit_scheduled','revisit_scheduled','won')
                               THEN stage ELSE 'new' END,
           -- a fresh start on the calling clock: consecutive misses and the 1h TAT
           miss_count   = CASE WHEN stage IN ('new','visit_scheduled','revisit_scheduled','won')
                               THEN miss_count ELSE 0 END,
           tat_deadline = CASE WHEN stage IN ('new','visit_scheduled','revisit_scheduled','won')
                               THEN tat_deadline ELSE now() + interval '1 hour' END
     WHERE id = NEW.entity_id::uuid;

    -- log the move like any other, so Reports and the lead history see it
    IF v_before NOT IN ('new','visit_scheduled','revisit_scheduled','won') THEN
        INSERT INTO activity_log (id, entity_type, entity_id, action, field,
                                  before_value, after_value, metadata, created_at)
        VALUES (gen_random_uuid(), 'lead', NEW.entity_id, 'stage_change', 'stage',
                v_before, 'new', jsonb_build_object('reason', 'lead arrived again'), now());
    END IF;
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS activity_log_lead_repeat ON activity_log;
CREATE TRIGGER activity_log_lead_repeat
AFTER INSERT ON activity_log
FOR EACH ROW
WHEN (NEW.entity_type = 'lead'
      AND (NEW.action = 'lead_repeat'
           OR (NEW.action = 'meta_form_submitted'
               AND NEW.metadata->>'new_lead' = 'false'
               AND coalesce(NEW.metadata->>'merged', 'false') <> 'true')))
EXECUTE FUNCTION trg_lead_repeat_count();

-- 6. merge a new source into the existing lead for that phone
CREATE OR REPLACE FUNCTION trg_leads_merge_source()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_p10 text := right(regexp_replace(coalesce(NEW.phone, ''), '\D', '', 'g'), 10);
    v_id  uuid;
BEGIN
    IF NEW.sources = '{}' THEN
        NEW.sources := ARRAY[NEW.source];
    END IF;

    -- A key we already hold as a lead: a re-sync. ON CONFLICT (origin_key) absorbs it.
    IF EXISTS (SELECT 1 FROM leads WHERE origin_key = NEW.origin_key) THEN
        RETURN NEW;
    END IF;
    -- A key already merged into another lead: also a re-sync (the sheets re-insert
    -- every row every run). Skip silently — counting it would add one every 4 hours.
    IF EXISTS (SELECT 1 FROM leads WHERE merged_origin_keys @> ARRAY[NEW.origin_key]) THEN
        RETURN NULL;
    END IF;
    IF length(v_p10) <> 10 THEN
        RETURN NEW;
    END IF;

    -- same buyer under another source; prefer a live lead, then the newest
    SELECT id INTO v_id
      FROM leads
     WHERE right(regexp_replace(phone, '\D', '', 'g'), 10) = v_p10
     ORDER BY (stage IN ('won','future_prospect','rejected','rnr')), created_at DESC
     LIMIT 1;
    IF v_id IS NULL THEN
        RETURN NEW;
    END IF;

    UPDATE leads
       SET sources = CASE WHEN NEW.source = ANY(sources) THEN sources
                          ELSE sources || NEW.source END,
           merged_origin_keys = merged_origin_keys || NEW.origin_key
     WHERE id = v_id;

    -- fires activity_log_lead_repeat → count + stage.
    -- `lead` = everything the incoming row carried (city, budget, raw sheet row, …),
    -- since that row is never inserted and this entry is the only place it survives.
    -- Nulls and our own bookkeeping columns are dropped.
    INSERT INTO activity_log (id, entity_type, entity_id, action, metadata, created_at)
    VALUES (gen_random_uuid(), 'lead', v_id::text, 'lead_repeat',
            jsonb_build_object(
                'source',     NEW.source,
                'origin_key', NEW.origin_key,
                'name',       NEW.name,
                'lead',       jsonb_strip_nulls(to_jsonb(NEW)
                                  - 'id' - 'sources' - 'merged_origin_keys'
                                  - 'count_leads_repeat')),
            now());
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS leads_merge_source ON leads;
CREATE TRIGGER leads_merge_source
BEFORE INSERT ON leads
FOR EACH ROW
EXECUTE FUNCTION trg_leads_merge_source();

-- 7. recount only (never touches stage) — safe to re-run any time
UPDATE leads
   SET count_leads_repeat = lead_repeat_count(id)
 WHERE count_leads_repeat IS DISTINCT FROM lead_repeat_count(id);

-- 8. check
SELECT cardinality(sources) AS n_sources, count(*) FROM leads GROUP BY 1 ORDER BY 1;
SELECT count_leads_repeat, count(*) FROM leads GROUP BY 1 ORDER BY 1;
