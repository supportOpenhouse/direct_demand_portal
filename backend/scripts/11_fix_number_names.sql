-- fix_number_names() — leads whose NAME is just their phone number ("+91 85955 94789",
-- how the WhatsApp paths create a lead with no profile name) take the newest REAL name
-- a source merged into them carried (activity_log lead_repeat → metadata.lead.name).
--
-- A function so it can be re-run whenever: create it once (step 1), then call it (step
-- 2) as often as you like. Each rename is logged (action name_from_source, field name,
-- before → after). Safe to repeat: a renamed lead no longer matches the number
-- pattern, so a second call renames nothing it already renamed.
-- New merges don't need it — the leads_merge_source trigger renames on arrival
-- (07_lead_sources.sql); this catches everything merged before that, or by any other path.

-- 0. confirm prod
SELECT current_database(), inet_server_addr();

-- 1. create (or update) the function — run once
CREATE OR REPLACE FUNCTION fix_number_names()
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    n integer;
BEGIN
    WITH pick AS (
        SELECT DISTINCT ON (l.id)
               l.id, l.name AS old_name, btrim(a.metadata->'lead'->>'name') AS new_name,
               a.metadata->>'source' AS source
          FROM leads l
          JOIN activity_log a
            ON a.entity_id = l.id::text AND a.action = 'lead_repeat'
         WHERE coalesce(l.name, '') ~ '^\s*\+?[\d\s()-]{8,}\s*$'
           AND coalesce(btrim(a.metadata->'lead'->>'name'), '') <> ''
           AND a.metadata->'lead'->>'name' !~ '^\s*\+?[\d\s()-]{8,}\s*$'
         ORDER BY l.id, a.created_at DESC        -- the newest real name wins
    ), renamed AS (
        UPDATE leads SET name = p.new_name
          FROM pick p
         WHERE leads.id = p.id
        RETURNING leads.id
    )
    INSERT INTO activity_log (id, entity_type, entity_id, action, field,
                              before_value, after_value, metadata, created_at)
    SELECT gen_random_uuid(), 'lead', p.id::text, 'name_from_source', 'name',
           p.old_name, p.new_name,
           jsonb_build_object('source', p.source, 'via', 'fix_number_names'), now()
      FROM pick p JOIN renamed r ON r.id = p.id;

    GET DIAGNOSTICS n = ROW_COUNT;   -- one log row per renamed lead
    RETURN n;
END $$;

-- 2. run it — any time, as often as needed; returns how many leads it renamed
SELECT fix_number_names() AS renamed;

-- 3. check: what's still named after a number (no merged source knows a real name)
SELECT count(*) AS still_number_named
  FROM leads WHERE coalesce(name, '') ~ '^\s*\+?[\d\s()-]{8,}\s*$';
