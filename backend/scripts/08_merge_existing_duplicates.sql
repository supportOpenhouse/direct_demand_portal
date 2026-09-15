-- Merge leads that ALREADY share a phone (last 10 digits) — the ones created before the
-- leads_merge_source trigger existed. Needs 07_lead_sources.sql applied first.
--
-- Per phone: keep the OLDEST lead (created_at, then received_at, then id as the final
-- tiebreak), fold every newer one into it, delete the newer ones.
--   * children MOVE to the kept lead first. Deleting first would be destructive:
--     lead_notes / visits / crm_visits / dial_queue / lead_confirmed_data are
--     ON DELETE CASCADE, call_logs / huvo_call_updates are SET NULL.
--   * dial_queue is unique per (campaign, lead): where both leads sit in the same
--     campaign, the kept lead's entry stays and the newer one's is dropped.
--   * lead_confirmed_data is one row per lead: moved only if the kept lead has none;
--     otherwise the newer one's is copied into the log entry before it cascades away.
--   * the newer lead's activity history is re-pointed to the kept lead.
--   * one `lead_repeat` entry per deleted lead, with its whole row in metadata.lead,
--     dated at that lead's own created_at. That fires activity_log_lead_repeat →
--     count_leads_repeat recount + stage → 'new' (unless visit/revisit/won).
--   * the deleted lead's origin_key goes into merged_origin_keys, so the sheet re-sync
--     can't recreate it.
-- One call is one statement, so it is atomic: all of a phone or none of it.

CREATE OR REPLACE FUNCTION merge_duplicate_leads(p_phone10 text)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    v_keep uuid;
    r      leads%ROWTYPE;
    n      integer := 0;
BEGIN
    SELECT id INTO v_keep
      FROM leads
     WHERE right(regexp_replace(phone, '\D', '', 'g'), 10) = p_phone10
     ORDER BY created_at, received_at NULLS LAST, id
     LIMIT 1;
    IF v_keep IS NULL THEN
        RETURN 0;
    END IF;

    FOR r IN
        SELECT * FROM leads
         WHERE right(regexp_replace(phone, '\D', '', 'g'), 10) = p_phone10
           AND id <> v_keep
         ORDER BY created_at, received_at NULLS LAST, id
    LOOP
        -- notes: the thread is lead_notes PLUS the " | "-joined source_remarks on the
        -- lead row itself. lead_notes move by lead_id; the remarks would die with the
        -- row, so each becomes a note on the kept lead, attributed to its own source
        -- ('remarks' = the thread's "imported" style) and dated when that lead arrived.
        UPDATE lead_notes        SET lead_id = v_keep WHERE lead_id = r.id;
        INSERT INTO lead_notes (id, lead_id, body, author, source, created_at)
        SELECT gen_random_uuid(), v_keep, btrim(part), 'From ' || r.source, 'remarks', r.created_at
          FROM unnest(string_to_array(coalesce(r.source_remarks, ''), ' | ')) AS part
         WHERE btrim(part) <> '';

        UPDATE visits            SET lead_id = v_keep WHERE lead_id = r.id;
        UPDATE crm_visits        SET lead_id = v_keep WHERE lead_id = r.id;
        UPDATE call_logs         SET lead_id = v_keep WHERE lead_id = r.id;
        UPDATE huvo_call_updates SET lead_id = v_keep WHERE lead_id = r.id;

        DELETE FROM dial_queue d
         WHERE d.lead_id = r.id
           AND EXISTS (SELECT 1 FROM dial_queue k
                        WHERE k.lead_id = v_keep AND k.campaign_id = d.campaign_id);
        UPDATE dial_queue SET lead_id = v_keep WHERE lead_id = r.id;

        IF NOT EXISTS (SELECT 1 FROM lead_confirmed_data WHERE lead_id = v_keep) THEN
            UPDATE lead_confirmed_data SET lead_id = v_keep WHERE lead_id = r.id;
        END IF;

        UPDATE activity_log
           SET entity_id = v_keep::text
         WHERE entity_type = 'lead' AND entity_id = r.id::text;

        UPDATE leads
           SET sources = CASE WHEN r.source = ANY(sources) THEN sources
                              ELSE sources || r.source END,
               merged_origin_keys = merged_origin_keys || r.origin_key
         WHERE id = v_keep;

        INSERT INTO activity_log (id, entity_type, entity_id, action, metadata, created_at)
        VALUES (gen_random_uuid(), 'lead', v_keep::text, 'lead_repeat',
                jsonb_build_object(
                    'source',          r.source,
                    'origin_key',      r.origin_key,
                    'name',            r.name,
                    'merged_existing', true,
                    'lead',            jsonb_strip_nulls(to_jsonb(r)
                                           - 'sources' - 'merged_origin_keys'
                                           - 'count_leads_repeat'),
                    -- only non-null when the kept lead already had its own and this
                    -- one's is about to cascade away with the delete
                    'confirmed_data',  (SELECT to_jsonb(c) FROM lead_confirmed_data c
                                         WHERE c.lead_id = r.id)),
                r.created_at);

        DELETE FROM leads WHERE id = r.id;
        n := n + 1;
    END LOOP;
    RETURN n;
END $$;


-- ── 1. PREVIEW one phone (read-only) ───────────────────────────────────────────
SELECT CASE WHEN row_number() OVER (ORDER BY created_at, received_at NULLS LAST, id) = 1
            THEN 'KEEP' ELSE 'DELETE' END AS action,
       id, origin_key, source, name, stage, assigned_to, created_at
  FROM leads
 WHERE right(regexp_replace(phone, '\D', '', 'g'), 10) = '8003297088'
 ORDER BY created_at, received_at NULLS LAST, id;

-- ── 2. APPLY one phone ─────────────────────────────────────────────────────────
-- SELECT merge_duplicate_leads('8003297088');

-- ── 3. VERIFY one phone ────────────────────────────────────────────────────────
-- SELECT id, name, stage, sources, merged_origin_keys, count_leads_repeat
--   FROM leads WHERE right(regexp_replace(phone, '\D', '', 'g'), 10) = '8003297088';
-- SELECT action, before_value, after_value, metadata->>'origin_key' AS merged, created_at
--   FROM activity_log
--  WHERE entity_id = (SELECT id::text FROM leads
--                      WHERE right(regexp_replace(phone, '\D', '', 'g'), 10) = '8003297088')
--  ORDER BY created_at DESC;

-- ── 4. ALL phones — only after the one-phone run is confirmed ───────────────────
-- SELECT p10, merge_duplicate_leads(p10) AS deleted
--   FROM (SELECT right(regexp_replace(phone, '\D', '', 'g'), 10) AS p10
--           FROM leads
--          WHERE length(right(regexp_replace(phone, '\D', '', 'g'), 10)) = 10
--          GROUP BY 1 HAVING count(*) > 1) d;
