-- title_case_names() — every lead name as "First Letter Capital Of Every Word"
-- ("saransh KHERA" → "Saransh Khera"). Create once (step 1), call whenever (step 2).
--
-- title_case(text), the rule — tested against real prod names before it was written:
--   * a word starts after a space . , / or -   → "J.K Joshi", "Dr.Sharma", "(Mbbs,Md)",
--     "Singh/Broker", "Sharma-Verma". NOT after an apostrophe → "It's", not "It'S".
--   * the first LETTER of each word is capitalised, skipping leading punctuation
--     → "[DEALER]" becomes "[Dealer]", not "[dealer]".
--   * the rest of a word is lowercased ONLY if it has no lowercase letters of its own:
--     "BALRAM" → "Balram", but a name already mixing cases keeps its inner capitals
--     ("HemaInHarmony", "McDonald").
--   * runs of spaces collapse to one; the name is trimmed.
--   Postgres' own initcap() was rejected: it starts a word after ANY non-letter, which on
--   prod gave "It'S", "Name@Gmail.Com" and ALL-CAPS on decoratively written names.
--
-- title_case_names() applies it to leads.name. Skipped: a name that is only a phone
-- number (fix_number_names() replaces those) and anything containing '@' (an email, not
-- a name). Not logged to activity_log — formatting only; an entry per lead would bury
-- every lead's history under "sushma singh → Sushma Singh". Safe to repeat: only names
-- that would actually change are written.

-- 0. confirm prod
SELECT current_database(), inet_server_addr();

-- 1. create (or update) the functions — run once
CREATE OR REPLACE FUNCTION title_case(p text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT string_agg(
             CASE WHEN seg !~ '[[:alpha:]]' THEN seg
                  ELSE substring(seg from '^[^[:alpha:]]*')
                       || upper(substring(seg from '[[:alpha:]]'))
                       || CASE WHEN r ~ '[[:lower:]]' THEN r ELSE lower(r) END
             END, '' ORDER BY i)
      FROM (SELECT seg, i,
                   coalesce(substring(seg from '^[^[:alpha:]]*[[:alpha:]](.*)$'), '') AS r
              FROM regexp_split_to_table(regexp_replace(btrim(p), '\s+', ' ', 'g'),
                                         '(?<=[\s.,/-])')
                   WITH ORDINALITY AS t(seg, i)) x
$$;

CREATE OR REPLACE FUNCTION title_case_names()
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    n integer;
BEGIN
    UPDATE leads
       SET name = title_case(name)
     WHERE coalesce(btrim(name), '') <> ''
       AND name !~ '^\s*\+?[\d\s()-]{8,}\s*$'
       AND name NOT LIKE '%@%'
       AND name IS DISTINCT FROM title_case(name);
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;

-- 2. run it — any time; returns how many names it changed
SELECT title_case_names() AS renamed;

-- 3. check: nothing left to change
SELECT count(*) AS not_title_case
  FROM leads
 WHERE coalesce(btrim(name), '') <> ''
   AND name !~ '^\s*\+?[\d\s()-]{8,}\s*$'
   AND name NOT LIKE '%@%'
   AND name IS DISTINCT FROM title_case(name);
