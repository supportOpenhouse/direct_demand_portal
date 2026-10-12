#!/usr/bin/env node
/* The Search page's field-search rules — parse, fuzzy match, and what the box offers at
   the cursor. Runs the REAL src/lib/leadQuery.ts (bundled with esbuild), like
   check-lead-filters.mjs.

     node scripts/check-lead-query.mjs */
import assert from "node:assert/strict";
import { build } from "esbuild";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { writeFileSync, rmSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const bundled = await build({
  entryPoints: [join(here, "../src/lib/leadQuery.ts")],
  bundle: true, platform: "node", format: "esm", jsx: "automatic",
  write: false, logLevel: "silent",
});
const out = join(tmpdir(), `lead-query-${process.pid}.mjs`);
writeFileSync(out, bundled.outputFiles[0].text);
const m = await import(pathToFileURL(out).href);
rmSync(out);

// ── fuzzy ─────────────────────────────────────────────────────────────────────
assert.ok(m.fuzzyMatch("noida", "Greater Noida West"), "substring");
assert.ok(m.fuzzyMatch("noda", "Noida"), "one typo in a 4-letter word");
assert.ok(m.fuzzyMatch("gurgoan", "Gurgaon"), "a swap counts as one typo");
assert.ok(m.fuzzyMatch("sobah", "Sobha City"), "typo against a word prefix");
assert.ok(m.fuzzyMatch("98765 43", "+91 98765 43210"), "digits compared as digits");
assert.ok(m.fuzzyMatch("rahul sing", "Rahul Singh"), "every word must match");
assert.ok(!m.fuzzyMatch("rnr", "rent"), "3 letters allow no typo");
assert.ok(!m.fuzzyMatch("ghaziabad", "Gurgaon"), "a different word is not a typo");
assert.ok(!m.fuzzyMatch("x", null), "an empty value never matches");

// ── parse ─────────────────────────────────────────────────────────────────────
const p = m.parseQuery('city:"noida" AND stage:qualified OR rm:"anant"');
assert.deepEqual(p.groups, [[{ field: "city", text: "noida" }, { field: "stage", text: "qualified" }],
                            [{ field: "rm", text: "anant" }]], "AND binds tighter than OR");
assert.deepEqual(m.parseQuery('city:"noida" stage:"new"').groups.length, 1, "adjacent clauses = AND");
assert.deepEqual(m.parseQuery('"sobha"').groups, [[{ field: "any", text: "sobha" }]], "bare quotes = any field");
assert.deepEqual(m.parseQuery('City:"x" and RM:"y"').groups[0].map((c) => c.field), ["city", "rm"], "case-insensitive");
assert.deepEqual(m.parseQuery('city:"noi').groups, [[{ field: "city", text: "noi" }]], "an unclosed quote still searches");
assert.match(m.parseQuery('colour:"red"').errors[0], /unknown field/);
assert.match(m.parseQuery("noida").errors[0], /wrap free text/);

// ── evaluate ──────────────────────────────────────────────────────────────────
const lead = (o) => ({ name: null, phone: null, email: null, city: null, societies: [], source: "meta", sources: [],
  stage: "new", qualified_status: null, assigned_to: null, budget_band: null, configuration: null, plan_to_buy: null,
  preferred_visit_day: null, latest_note: null, source_remarks: null, reject_reason: null, reject_notes: null,
  visit_society: null, visit_status: null, visit_rm: null, buyer_profession: null, buyer_property_type: null, ...o });
const a = lead({ city: "Noida", stage: "qualified", assigned_to: "Saumya Behera" });
const b = lead({ city: "Gurgaon", stage: "new", assigned_to: "Anant Srivastava" });
const q = (s, l) => m.matchesQuery(l, m.parseQuery(s));
assert.ok(q('city:"noida" AND stage:"qualified"', a) && !q('city:"noida" AND stage:"qualified"', b));
assert.ok(q('city:"noida" OR rm:"anant"', a) && q('city:"noida" OR rm:"anant"', b), "OR");
assert.ok(q('stage:"qualified"', a), "stage by its key");
assert.ok(q('stage:"Qualified Leads"', a) || q('stage:"Qualified"', a), "stage by its label");
assert.ok(q('city:""', b), 'an empty field:"" matches everything');
assert.ok(q('"saumya"', a) && !q('"saumya"', b), "any field");
assert.ok(q("", b), "empty query = everything");

// ── cursor ────────────────────────────────────────────────────────────────────
const at = (s) => m.cursorContext(s, s.length);
assert.deepEqual(at('city:"noi'), { kind: "value", field: "city", partial: "noi", from: 6 });
assert.deepEqual(at('city:"noida"'), { kind: "joiner" }, "after a closed quote → +AND / +OR");
assert.deepEqual(at('city:"noida" '), { kind: "joiner" });
assert.deepEqual(at('city:"noida" AND '), { kind: "field", partial: "", from: 17 }, "after AND → fields");
assert.deepEqual(at('city:"noida" AND st'), { kind: "field", partial: "st", from: 17 });
assert.deepEqual(at(""), { kind: "field", partial: "", from: 0 }, "empty box → fields");
assert.equal(m.cursorContext('city:"noida" AND rm:"a"', 9).kind, "value", "cursor back inside an earlier value");
assert.equal(m.fieldSuggestions("st")[0].key, "stage");
assert.equal(m.fieldSuggestions("hot")[0].key, "warmth", "label match");

const vals = m.valueSuggestions([a, b, lead({ city: "noida" })], "city", "no");
assert.deepEqual(vals, [{ value: "Noida", count: 2 }], "case-merged, counted");
assert.deepEqual(m.valueSuggestions([a], "phone", ""), [], "no suggestions for identifiers");

console.log("lead query: all checks passed");
