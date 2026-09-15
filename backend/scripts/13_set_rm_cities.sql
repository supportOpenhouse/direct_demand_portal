-- Cities each RM takes new leads for (users.city). Drives the hourly round-robin and
-- the admin "Add lead": a lead whose city some RM covers goes to one of those RMs;
-- any other city (blank, a typo, a city nobody covers) goes to any RM.
--
-- Keyed by EMAIL, not name: unique, and immune to a second "Rahul Singh" joining.
-- Spellings match leads.city exactly (the match is case-insensitive anyway).
-- Idempotent: re-running sets the same arrays.

-- 0. confirm prod
SELECT current_database(), inet_server_addr();

-- 1. set cities
UPDATE users SET city = ARRAY['Noida', 'Ghaziabad']
 WHERE email IN ('saumya.behera@openhouse.in', 'avinash.chaturvedi@openhouse.in');

UPDATE users SET city = ARRAY['Gurgaon']
 WHERE email IN ('rinku.hira@openhouse.in', 'rahul.singh2@openhouse.in', 'pankaj.singh@openhouse.in');

-- 2. check: every active RM and what they cover (expect 2 × Noida+Ghaziabad, 3 × Gurgaon;
--    OH Support is test_rm and never takes real leads, so empty is correct)
SELECT name, email, role, city
  FROM users
 WHERE active AND role IN ('rm', 'test_rm')
 ORDER BY role, name;
