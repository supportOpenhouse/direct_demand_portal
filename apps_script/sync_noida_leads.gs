/**
 * Openhouse Direct Demand — "Noida Leads 10 Sep Onwards" → Neon, directly.
 *
 * Apps Script's JDBC service covers Cloud SQL / MySQL / SQL Server / Oracle only —
 * there is no Postgres driver — so this uses Neon's SQL-over-HTTP endpoint instead,
 * which UrlFetchApp can reach. Verified against this database: parameterised queries
 * and the batch/transaction form both work.
 *
 * Names are prefixed ND_ because Apps Script puts every .gs file in one shared global
 * scope; this has to coexist with anything else bound to the Sheet.
 *
 * ── Setup ────────────────────────────────────────────────────────────────────
 * 1. Run the DDL below ONCE (Neon SQL Editor). Safe to re-run; the backend's own
 *    migrations issue the identical statements, so a deploy won't conflict.
 *
 *      ALTER TABLE meta_leads ADD COLUMN IF NOT EXISTS configuration    TEXT;
 *      ALTER TABLE meta_leads ADD COLUMN IF NOT EXISTS current_location TEXT;
 *      ALTER TABLE meta_leads ADD COLUMN IF NOT EXISTS zip_code         TEXT;
 *      ALTER TABLE leads      ADD COLUMN IF NOT EXISTS current_location TEXT;
 *      ALTER TABLE leads      ADD COLUMN IF NOT EXISTS zip_code         TEXT;
 *
 * 2. Sheet → Extensions → Apps Script. Paste this in as a new .gs file.
 * 3. Project Settings → Script Properties → add:
 *      NEON_URL = postgresql://<user>:<pass>@<endpoint>.neon.tech/neondb?sslmode=require
 * 4. Run ND_runSync once, read the log. Then ND_installTrigger for hourly.
 *
 * ⚠ NEON_URL is a full database credential. Everyone with edit access to this Sheet
 *   can read it in Script Properties, and it grants far more than inserting leads.
 *   Use a Neon role scoped to INSERT on meta_leads + leads if you can.
 *
 * Re-running over the whole sheet is safe: both inserts are ON CONFLICT DO NOTHING,
 * keyed the same way the 4-hourly cron keys its own Meta rows, so the same buyer on
 * both forms stays one lead.
 */

const ND_SHEET_NAME = 'Noida Leads 10 Sep Onwards';
const ND_BATCH_SIZE = 200;   // rows per HTTP round trip

/* The Noida form asks the same questions in longer words. Renamed onto the column
   they belong in rather than added as new ones. Three more need no entry: the
   normaliser strips the trailing '?', so `your_budget_range?`,
   `preferred_site_visit_day?` and `full_name` already land correctly. */
const ND_HEADER_ALIASES = {
  // `city` is the demand side everywhere in this app — where they want to BUY.
  // Where they live now is its own column, and the two must not be swapped.
  'where_are_you_looking_to_buy_a_home': 'city',
  'where_do_you_currently_live': 'current_location',
  'which_flat_apartment_size_do_you_need': 'configuration',
};

/* ── normalisers ──────────────────────────────────────────────────────────────
   Mirrors of backend/app/services/normalize.py and leads_sync.py. They are
   duplicated because the script talks to the database directly and so has to do the
   work the server would have done. Change one, change the other — a lead whose city
   isn't normalised the same way falls out of every city filter. */

// A failed sheet formula renders as an error literal and reads back as ordinary
// text, so '#N/A' would otherwise be stored as a city.
const ND_SHEET_ERRORS = /^#(N\/A|REF!|VALUE!|DIV\/0!|NAME\?|NUM!|NULL!|ERROR!)$/i;

function ND_cell_(v) {
  const s = String(v == null ? '' : v).trim();
  return ND_SHEET_ERRORS.test(s) ? '' : s;
}

function ND_header_(h) {
  const key = String(h).trim().toLowerCase().replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  return ND_HEADER_ALIASES[key] || key;
}

// Python's str.title(): first letter of each alphabetic run, rest lowered.
function ND_title_(s) {
  return s.replace(/[A-Za-z]+/g, w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());
}

// Every phone comparison in this app is the last 10 digits. 'p:+919876543210' and
// '91-9876543210' are the same person.
function ND_phone10_(raw) {
  const d = String(raw == null ? '' : raw).replace(/\D/g, '');
  return d.length >= 10 ? d.slice(-10) : '';
}

function ND_displayPhone_(p10) {
  return '+91 ' + p10.slice(0, 5) + ' ' + p10.slice(5);
}

function ND_name_(raw) {
  const s = String(raw == null ? '' : raw).trim().replace(/^@+/, '').replace(/_/g, ' ').trim();
  return s || null;
}

// 'up_to_₹75_lacs' -> 'Up to ₹75 lacs'
function ND_prettyEnum_(raw) {
  if (!raw) return null;
  const s = String(raw).replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : null;
}

function ND_city_(raw) {
  if (raw == null) return null;
  const s = String(raw).trim().toLowerCase();
  if (!s) return null;
  if (s.indexOf('noida') >= 0) return 'Noida';
  if (s.indexOf('gurgaon') >= 0 || s.indexOf('gurugram') >= 0) return 'Gurgaon';
  if (s.indexOf('ghaziabad') >= 0) return 'Ghaziabad';
  if (s.indexOf('faridabad') >= 0) return 'Faridabad';
  if (s.indexOf('delhi') >= 0) return 'Delhi';
  return ND_title_(String(raw).trim());
}

// Qualifiers that make a config genuinely different are kept, never merged away:
// '2 BHK + Study' stays distinct from '2 BHK'.
const ND_CONFIG_EXTRAS = [
  [/\bstudy\b/, 'Study'],
  [/\bservant\b|\bmaid\b|\bs\.?q\.?\b|\bservant\s*quarter\b/, 'Servant'],
  [/\bpooja\b|\bpuja\b|\bmandir\b/, 'Pooja'],
  [/\butility\b/, 'Utility'],
  [/\bstore\b|\bstorage\b/, 'Store'],
];

function ND_config_(raw) {
  if (raw == null) return null;
  const s = String(raw).trim().toLowerCase();
  if (!s) return null;
  if (s.indexOf('studio') >= 0) return 'Studio';
  const m = s.match(/(\d+(?:\.\d+)?)/);
  if (!m) return ND_title_(String(raw).trim());
  let n = m[1];
  if (n.slice(-2) === '.0') n = n.slice(0, -2);
  const unit = /\brk\b/.test(s) ? 'RK' : 'BHK';
  const extras = ND_CONFIG_EXTRAS.filter(p => p[0].test(s)).map(p => p[1]);
  return extras.length ? n + ' ' + unit + ' + ' + extras.join(' + ') : n + ' ' + unit;
}

/* ── Neon SQL over HTTP ───────────────────────────────────────────────────── */

/**
 * Run statements against Neon. Pass an array and they run inside ONE transaction,
 * which is what keeps a batch's meta_leads and leads rows from landing apart.
 */
function ND_sql_(statements) {
  const conn = PropertiesService.getScriptProperties().getProperty('NEON_URL');
  if (!conn) throw new Error('Set NEON_URL in Script Properties first.');
  const host = conn.match(/@([^\/?]+)\//)[1];
  const many = statements.length > 1;

  const resp = UrlFetchApp.fetch('https://' + host + '/sql', {
    method: 'post',
    contentType: 'application/json',
    headers: many
      ? { 'Neon-Connection-String': conn, 'Neon-Batch-Isolation-Level': 'ReadCommitted' }
      : { 'Neon-Connection-String': conn },
    payload: JSON.stringify(many ? { queries: statements } : statements[0]),
    muteHttpExceptions: true,
  });

  const code = resp.getResponseCode();
  const body = resp.getContentText();
  if (code >= 300) throw new Error('Neon HTTP ' + code + ': ' + body);
  const out = JSON.parse(body);
  return many ? out.results : [out];
}

/* jsonb_to_recordset, rather than a VALUES list with $1..$2800: one parameter per
   statement whatever the batch size, so there is no placeholder arithmetic to get
   wrong and no bind-parameter ceiling to chunk around.

   `id` is supplied explicitly. It looks like it has a default, but the default is
   uuid.uuid4 on the SQLAlchemy model — CLIENT side. The column itself is NOT NULL
   with nothing behind it, so a raw INSERT that omits id fails with 23502. */
const ND_INSERT_RAW = `
INSERT INTO meta_leads (id, dedupe_key, full_name, phone, email, city, society,
                        budget_range, plan_to_buy, preferred_visit_day,
                        configuration, current_location, zip_code, is_test, raw)
SELECT gen_random_uuid(), r.dedupe_key, r.full_name, r.phone, r.email, r.city, NULL,
       r.budget_range, NULL, r.preferred_visit_day,
       r.configuration, r.current_location, r.zip_code, false, r.raw
  FROM jsonb_to_recordset($1::jsonb) AS r(
       dedupe_key text, full_name text, phone text, email text, city text,
       budget_range text, preferred_visit_day text, configuration text,
       current_location text, zip_code text, raw jsonb)
 ON CONFLICT (dedupe_key) DO NOTHING`;

/* origin_key is 'meta:<phone10>' — the SAME key the 4-hourly cron uses for its Meta
   rows, deliberately. A different one here would double every buyer who appears on
   both forms. stage and id come from their column defaults. */
const ND_INSERT_LEAD = `
INSERT INTO leads (id, origin_key, source_category, source, name, phone, email, city,
                   configuration, budget_band, preferred_visit_day,
                   current_location, zip_code, is_test, received_at, tat_deadline,
                   source_meta)
SELECT gen_random_uuid(), r.origin_key, 'meta', 'meta', r.name, r.phone, r.email, r.city,
       r.configuration, r.budget_band, r.preferred_visit_day,
       r.current_location, r.zip_code, false, now(), now() + interval '1 hour',
       r.source_meta
  FROM jsonb_to_recordset($1::jsonb) AS r(
       origin_key text, name text, phone text, email text, city text,
       configuration text, budget_band text, preferred_visit_day text,
       current_location text, zip_code text, source_meta jsonb)
 ON CONFLICT (origin_key) DO NOTHING`;

/* ── the sync ─────────────────────────────────────────────────────────────── */

function ND_installTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'ND_runSync') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('ND_runSync').timeBased().everyHours(1).create();
  Logger.log('Trigger installed: ND_runSync, hourly.');
}

function ND_runSync() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ND_SHEET_NAME);
  if (!sheet) throw new Error('Sheet "' + ND_SHEET_NAME + '" not found');

  const values = sheet.getDataRange().getValues();
  if (values.length < 2) { Logger.log('Sheet has no data rows.'); return; }

  const headers = values[0].map(ND_header_);
  const seen = {};       // the same number twice in one run would violate the unique
  const raws = [];       // key inside a single statement, which DO NOTHING can't fix
  const leads = [];

  for (let i = 1; i < values.length; i++) {
    const row = {};
    for (let j = 0; j < headers.length; j++) {
      if (!headers[j]) continue;
      let v = values[i][j];
      // A Date would serialise as UTC and shift back a day across the IST boundary.
      if (v instanceof Date) v = Utilities.formatDate(v, 'Asia/Kolkata', 'yyyy-MM-dd');
      row[headers[j]] = ND_cell_(v);
    }

    // The phone IS the identity and the dedupe key, so a row without one can't be
    // stored. A half-filled form row is normal, not an error.
    const p10 = ND_phone10_(row.phone_number);
    if (!p10 || seen[p10]) continue;
    seen[p10] = true;

    const city = ND_city_(row.city);
    const config = ND_config_(row.configuration);
    const current = ND_city_(row.current_location);
    const budget = ND_prettyEnum_(row.your_budget_range);
    const visitDay = ND_prettyEnum_(row.preferred_site_visit_day);
    const zip = row.zip_code || null;
    const email = row.email || null;
    const name = ND_name_(row.full_name);
    const phone = ND_displayPhone_(p10);

    raws.push({
      dedupe_key: p10, full_name: name, phone: phone, email: email, city: city,
      budget_range: budget, preferred_visit_day: visitDay, configuration: config,
      current_location: current, zip_code: zip,
      raw: row,   // the whole sheet row, so nothing is lost to a column we didn't map
    });
    leads.push({
      origin_key: 'meta:' + p10, name: name, phone: phone, email: email, city: city,
      configuration: config, budget_band: budget, preferred_visit_day: visitDay,
      current_location: current, zip_code: zip,
      source_meta: {
        created_from: 'apps_script:noida_leads', budget_range: budget,
        preferred_visit_day: visitDay, city: city, configuration: config,
        current_location: current, zip_code: zip,
      },
    });
  }

  const batches = Math.ceil(raws.length / ND_BATCH_SIZE);
  Logger.log(raws.length + ' unique rows with a phone → ' + batches + ' batch(es).');

  let newRaw = 0, newLeads = 0;
  for (let b = 0; b < batches; b++) {
    const lo = b * ND_BATCH_SIZE, hi = lo + ND_BATCH_SIZE;
    const res = ND_sql_([
      { query: ND_INSERT_RAW,  params: [JSON.stringify(raws.slice(lo, hi))] },
      { query: ND_INSERT_LEAD, params: [JSON.stringify(leads.slice(lo, hi))] },
    ]);
    newRaw += res[0].rowCount || 0;
    newLeads += res[1].rowCount || 0;
    Logger.log('Batch ' + (b + 1) + '/' + batches + ' → raw +' + res[0].rowCount +
               ', leads +' + res[1].rowCount);
  }

  Logger.log('DONE — ' + raws.length + ' rows offered, ' + newRaw +
             ' new raw rows, ' + newLeads + ' new leads (the rest already existed).');
}
