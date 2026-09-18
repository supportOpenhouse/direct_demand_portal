-- crm_visits follows Openhouse Core: whenever app_visit_data gets a visit (insert or
-- refresh), the matching crm_visits row (same visit_id) takes Core's latest values.
-- Run top to bottom on prod; idempotent.
--
-- Rules:
--   * Core only ever ADDS information here. A NULL — or a blank: Core sends '' for
--     feedback nobody wrote (66 rows on 18 Sep held real sheet feedback against Core's '')
--     — keeps what crm_visits already has.
--   * a `found = false` refresh only flips the flag; its data columns are the last copy,
--     not news, so the trigger skips it.
--   * selected_time is folded to the spaced form ("3-5 PM" → "3 - 5 PM"), the one spelling
--     crm_visits holds since scripts/19 — Core returns both.
--   * a status MOVE is logged as visit_<status>, same shape visits_sync writes for the
--     sheet, with via = 'core'. Nothing else is an event. No-op refreshes write nothing.
--   * the lead's stage is NOT touched — same as the cancel endpoint and the sheet sync.
--   * not mirrored: booked_by, smid, rm_accompanying, buyer_name/mobile, source — those
--     record what WE sent when booking.
--
-- ⚠️ visits_sync (ops sheet, every 30 min) still writes status / visit_date / feedback.
-- Where the sheet and Core disagree, the two will overwrite each other on every run.

-- 0. confirm prod
SELECT current_database(), inet_server_addr();

-- 1. the trigger
CREATE OR REPLACE FUNCTION trg_crm_visits_from_core()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    cur crm_visits%ROWTYPE;
    nxt crm_visits%ROWTYPE;
BEGIN
    SELECT * INTO cur FROM crm_visits WHERE visit_id = NEW.visit_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN NULL;  -- a visit we didn't book
    END IF;

    nxt := cur;
    nxt.status         := coalesce(nullif(btrim(NEW.status), ''), cur.status);
    nxt.selected_date  := coalesce(NEW.selected_date::text, cur.selected_date);
    nxt.visit_date     := coalesce(NEW.visit_date::text, cur.visit_date);
    nxt.selected_time  := coalesce(regexp_replace(upper(nullif(btrim(NEW.selected_time), '')),
                                                  '\s*-\s*', ' - ', 'g'), cur.selected_time);
    nxt.buyer_feedback := coalesce(nullif(btrim(NEW.buyer_feedback), ''), cur.buyer_feedback);
    nxt.sales_feedback := coalesce(nullif(btrim(NEW.sales_feedback), ''), cur.sales_feedback);
    nxt.home_id        := coalesce(NEW.home_id, cur.home_id);
    nxt.society        := coalesce(nullif(btrim(NEW.society_name), ''), cur.society);
    nxt.city           := coalesce(nullif(btrim(NEW.city), ''), cur.city);

    IF nxt IS NOT DISTINCT FROM cur THEN
        RETURN NULL;
    END IF;

    UPDATE crm_visits
       SET status = nxt.status, selected_date = nxt.selected_date, visit_date = nxt.visit_date,
           selected_time = nxt.selected_time, buyer_feedback = nxt.buyer_feedback,
           sales_feedback = nxt.sales_feedback, home_id = nxt.home_id,
           society = nxt.society, city = nxt.city
     WHERE id = cur.id;

    IF nxt.status IS DISTINCT FROM cur.status THEN
        -- no actor: the change happened at Openhouse, not in this app
        INSERT INTO activity_log (id, entity_type, entity_id, action, field,
                                  before_value, after_value, metadata, created_at)
        VALUES (gen_random_uuid(), 'lead', cur.lead_id::text, 'visit_' || nxt.status,
                'visit_status', cur.status, nxt.status,
                jsonb_build_object('visit_id', cur.visit_id, 'via', 'core'), now());
    END IF;
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS app_visit_data_to_crm_visits ON app_visit_data;
CREATE TRIGGER app_visit_data_to_crm_visits
AFTER INSERT OR UPDATE ON app_visit_data
FOR EACH ROW WHEN (NEW.found)
EXECUTE FUNCTION trg_crm_visits_from_core();

-- 2. data: touch every row we booked so the trigger applies what Core already holds
UPDATE app_visit_data SET visit_id = visit_id
 WHERE found AND visit_id IN (SELECT visit_id FROM crm_visits);

-- 3. check: nothing Core holds (non-blank) still differs from crm_visits
SELECT count(*) AS still_differs
  FROM crm_visits c JOIN app_visit_data a USING (visit_id)
 WHERE a.found AND (
       (nullif(btrim(a.status), '') IS NOT NULL AND c.status IS DISTINCT FROM a.status)
    OR (a.selected_date IS NOT NULL AND c.selected_date IS DISTINCT FROM a.selected_date::text)
    OR (a.visit_date IS NOT NULL AND c.visit_date IS DISTINCT FROM a.visit_date::text)
    OR (nullif(btrim(a.sales_feedback), '') IS NOT NULL AND c.sales_feedback IS DISTINCT FROM btrim(a.sales_feedback))
    OR (nullif(btrim(a.buyer_feedback), '') IS NOT NULL AND c.buyer_feedback IS DISTINCT FROM btrim(a.buyer_feedback))
    OR (a.home_id IS NOT NULL AND c.home_id IS DISTINCT FROM a.home_id)
    OR (nullif(btrim(a.society_name), '') IS NOT NULL AND c.society IS DISTINCT FROM btrim(a.society_name))
    OR (nullif(btrim(a.city), '') IS NOT NULL AND c.city IS DISTINCT FROM btrim(a.city)));
