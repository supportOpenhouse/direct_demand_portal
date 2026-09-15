-- `lead_created` for EVERY lead, from every source — written by the database.
-- Run top to bottom on prod; idempotent.
--
-- Why a trigger: leads arrive by six paths (sheet cron, Apps Script over Neon HTTP,
-- Meta webhook, WhatsApp, Huvo, Add lead) and two of them never run Python. An
-- AFTER INSERT trigger is the one place every real insert passes through.
--   * a MERGED arrival never fires it: leads_merge_source (BEFORE INSERT) cancels that
--     insert and logs `lead_repeat` instead — no lead was created, so no entry.
--   * a re-sync conflict (ON CONFLICT DO NOTHING) inserts nothing, so no entry.
--   * who created it: source_meta.created_by (the WhatsApp / Huvo / Add lead paths set
--     it to the user's email), resolved to name + role from users. Sheet and Meta
--     leads have none — a job created them, actor stays NULL.
-- The app no longer logs `lead_created` itself; doing both would double every entry.

-- 0. confirm prod
SELECT current_database(), inet_server_addr();

-- 1. the trigger
CREATE OR REPLACE FUNCTION trg_lead_created()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_by text := NEW.source_meta->>'created_by';
BEGIN
    INSERT INTO activity_log (id, actor_email, actor_name, actor_role,
                              entity_type, entity_id, action, metadata, created_at)
    SELECT gen_random_uuid(), v_by, u.name, u.role,
           'lead', NEW.id::text, 'lead_created',
           jsonb_strip_nulls(jsonb_build_object(
               'source',       NEW.source,
               'name',         NEW.name,
               'origin_key',   NEW.origin_key,
               'created_from', NEW.source_meta->>'created_from',
               'assigned_to',  NEW.assigned_to)),
           NEW.created_at
      FROM (SELECT 1) AS one
      LEFT JOIN LATERAL (SELECT name, role FROM users
                          WHERE lower(email) = lower(v_by) LIMIT 1) u ON true;
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS leads_lead_created ON leads;
CREATE TRIGGER leads_lead_created
AFTER INSERT ON leads
FOR EACH ROW
EXECUTE FUNCTION trg_lead_created();

-- 2. data: every existing lead that has no entry, dated at its own created_at
INSERT INTO activity_log (id, actor_email, actor_name, actor_role,
                          entity_type, entity_id, action, metadata, created_at)
SELECT gen_random_uuid(), l.source_meta->>'created_by', u.name, u.role,
       'lead', l.id::text, 'lead_created',
       jsonb_strip_nulls(jsonb_build_object(
           'source',       l.source,
           'name',         l.name,
           'origin_key',   l.origin_key,
           'created_from', l.source_meta->>'created_from',
           'backfilled',   true)),
       l.created_at
  FROM leads l
  LEFT JOIN LATERAL (SELECT name, role FROM users
                      WHERE lower(email) = lower(l.source_meta->>'created_by') LIMIT 1) u ON true
 WHERE NOT EXISTS (SELECT 1 FROM activity_log a
                    WHERE a.action = 'lead_created' AND a.entity_type = 'lead'
                      AND a.entity_id = l.id::text);

-- 3. check: every lead has exactly one
SELECT count(*) AS leads,
       count(*) FILTER (WHERE n = 0) AS missing,
       count(*) FILTER (WHERE n > 1) AS duplicated
  FROM (SELECT l.id, (SELECT count(*) FROM activity_log a
                       WHERE a.action = 'lead_created' AND a.entity_id = l.id::text) AS n
          FROM leads l) x;
