/* Runnable check for the pushed-marker logic in sync_noida_leads.gs.
 *
 *   node apps_script/sync_noida_leads.test.js
 *
 * The marking is the only part of that file with real bookkeeping in it — sheet rows
 * skipped for being already-TRUE, duplicates riding along with their twin, and marks
 * that must survive a batch failing halfway. Everything else is a normaliser mirrored
 * from Python and covered by backend/tests/test_leads.py.
 *
 * Stubs the Apps Script host rather than mocking the script, so the real ND_runSync
 * runs end to end against a fake sheet and a fake Neon.
 */
const fs = require('fs');
const path = require('path');

let FETCHES = 0, FAIL_ON = -1, SHEET = null;

function makeSheet(grid) {
  return {
    grid,
    getDataRange: () => ({ getValues: () => grid.map(r => r.slice()) }),
    getLastColumn: () => Math.max(...grid.map(r => r.length)),
    getRange(row, col, nRows) {
      return {
        setValue: v => { grid[row - 1][col - 1] = v; },
        setValues: vals => {
          for (let i = 0; i < nRows; i++) {
            while (grid[row - 1 + i].length < col) grid[row - 1 + i].push('');
            grid[row - 1 + i][col - 1] = vals[i][0];
          }
        },
      };
    },
  };
}

const host = {
  SpreadsheetApp: { getActiveSpreadsheet: () => ({ getSheetByName: () => SHEET }), flush: () => {} },
  PropertiesService: {
    getScriptProperties: () => ({ getProperty: () => 'postgresql://u:p@h.neon.tech/neondb' }),
  },
  UrlFetchApp: {
    fetch: (url, opts) => {
      FETCHES++;
      if (FETCHES === FAIL_ON) return { getResponseCode: () => 500, getContentText: () => 'boom' };
      // ND_sql_ sends {query,params} for one statement and {queries:[…]} for many,
      // and unwraps the two responses differently. Mirror both so the harness keeps
      // working if a second statement is ever added back.
      const body = JSON.parse(opts.payload);
      const stmts = body.queries || [body];
      const counts = stmts.map(q => ({ rowCount: JSON.parse(q.params[0]).length }));
      return {
        getResponseCode: () => 200,
        getContentText: () => JSON.stringify(body.queries ? { results: counts } : counts[0]),
      };
    },
  },
  Utilities: { formatDate: d => d.toISOString().slice(0, 10) },
  Logger: { log: () => {} },
};
Object.assign(globalThis, host);
// The .gs is plain script-scope JS; eval'ing it here is what "loading" means.
eval(fs.readFileSync(path.join(__dirname, 'sync_noida_leads.gs'), 'utf8'));

let fails = 0;
const eq = (got, want, what) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g !== w) { console.log(`  FAIL ${what}\n       got  ${g}\n       want ${w}`); fails++; }
  else console.log(`  ok   ${what}`);
};

const H = ['where_do_you_currently_live?', 'where_are_you_looking_to_buy_a_home?',
  'your_budget_range?', 'which_flat/apartment_size_do_you_need?',
  'preferred_site_visit_day?', 'email', 'full_name', 'phone_number', 'zip_code'];
const row = (phone, name) =>
  ['Delhi', 'Greater Noida West', '₹1 cr', '3BHK', 'This Saturday', 'a@b.com', name, phone, '110092'];
const marks = () => SHEET.grid.slice(1).map(r => r[9]);

console.log('\n1. fresh sheet — marker column created; pushed TRUE, unpushable FALSE');
SHEET = makeSheet([H.slice(), row('9876543210', 'A'), row('', 'no phone'), row('9876500002', 'C')]);
FETCHES = 0; FAIL_ON = -1;
ND_runSync();
eq(SHEET.grid[0][9], 'pushed', 'header added on first run');
eq(marks(), [true, false, true], 'phoneless row is FALSE, not blank');

console.log('\n2. the same number twice — one push, both rows marked');
SHEET = makeSheet([H.slice(), row('9876543210', 'A'), row('91-9876543210', 'A again')]);
FETCHES = 0;
ND_runSync();
eq(marks(), [true, true], 'the duplicate is marked with its twin');
eq(FETCHES, 1, 'and cost no extra round trip');

console.log('\n3. TRUE is skipped; FALSE, blank and junk are all retried');
SHEET = makeSheet([H.concat(['pushed']),
  row('9876543210', 'boolean').concat([true]),
  row('9876500002', 'string').concat(['TRUE']),
  row('9876500003', 'false').concat([false]),
  row('9876500004', 'blank').concat(['']),
  row('9876500005', 'junk').concat(['maybe'])]);
FETCHES = 0;
ND_runSync();
eq(marks(), [true, 'TRUE', true, true, true], 'both TRUEs untouched, the other three now TRUE');
eq(FETCHES, 1, 'only the three retried rows were sent');

console.log('\n4. a batch that fails leaves the rest unmarked, to retry next run');
const many = [H.slice()];
for (let i = 0; i < 250; i++) many.push(row('98765' + String(100000 + i), 'R' + i));
SHEET = makeSheet(many);
FETCHES = 0; FAIL_ON = 2;               // batch 1 lands, batch 2 explodes
let threw = false;
try { ND_runSync(); } catch (e) { threw = true; }
eq(threw, true, 'the run fails loudly rather than reporting success');
eq(marks().filter(v => v === true).length, 200, 'exactly batch 1 is TRUE; 50 will retry');

console.log(fails ? `\n${fails} FAILED\n` : '\nall passed\n');
process.exit(fails ? 1 : 0);
