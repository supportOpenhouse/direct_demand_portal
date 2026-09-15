#!/usr/bin/env node
/* The shared lead-list filters' rules — the parts that would silently hide leads if
   they broke. Runs the REAL src/lib/leadFilters.ts (bundled on the fly with esbuild,
   which Vite already ships), not a hand-copied mirror that could drift from it.

     node scripts/check-lead-filters.mjs */
import assert from "node:assert/strict";
import { build } from "esbuild";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { writeFileSync, rmSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const bundled = await build({
  entryPoints: [join(here, "../src/lib/leadFilters.ts")],
  bundle: true, platform: "node", format: "esm", jsx: "automatic",
  write: false, logLevel: "silent",
});
const out = join(tmpdir(), `lead-filters-${process.pid}.mjs`);
writeFileSync(out, bundled.outputFiles[0].text);
const m = await import(pathToFileURL(out).href);
rmSync(out);

// ── invalid number: exactly 10 digits once a real leading +91 is removed ────────
assert.equal(m.isInvalidPhone("+91 98765 43210"), false, "the stored valid format");
assert.equal(m.isInvalidPhone("9876543210"), false, "a bare ten digits");
assert.equal(m.isInvalidPhone("91"), true, "the one invalid row prod actually has");
assert.equal(m.isInvalidPhone("+91 12345"), true, "too short after +91");
assert.equal(m.isInvalidPhone("+91 99999 999999"), true, "too long");
assert.equal(m.isInvalidPhone("919876543210"), true,
  "12 digits WITHOUT a +91 prefix must not be silently trimmed into a valid number");
assert.equal(m.isInvalidPhone(""), true, "blank is not a number");
assert.equal(m.isInvalidPhone(null), true, "null is not a number");

// ── society: master list + lead-only societies + none, all reconciling ───────────
const leads = [
  { society: "Gaur City 6" }, { society: "gaur city 6 " },   // same society, lead spelling
  { society: "Not In Master" },                              // a typo / missing project
  { society: "" }, { society: null },                        // no society
];
const master = ["Gaur City 6", "Zara Rossa"];
const opts = m.societyOptions(leads, (l) => l.society, master);
const label = Object.fromEntries(opts.map((o) => [o.value, o.label]));
assert.equal(label["Gaur City 6"], "Gaur City 6 (2)", "case/space-insensitive, master spelling wins");
assert.equal(label["Zara Rossa"], "Zara Rossa (0)", "a master society with no leads is still offered");
assert.equal(label["Not In Master"], "Not In Master (1)", "a society missing from master stays reachable");
const none = opts.find((o) => o.label.startsWith("— None —"));
assert.ok(none && none.label.endsWith("(2)"), "blank and null both count as no society");
const counted = opts.reduce((n, o) => n + Number(o.label.match(/\((\d+)\)$/)[1]), 0);
assert.equal(counted, leads.length, "every lead is reachable through exactly one option");
assert.ok(m.societyMatches("gaur city 6 ", "Gaur City 6"), "matching is case/space-insensitive");
assert.ok(m.societyMatches(null, none.value) && !m.societyMatches("x", none.value), "None means blank only");
assert.ok(
  m.societyOptions([], (l) => l.society, [], "Gone Society").some((o) => o.value === "Gone Society"),
  "an active selection faceting dropped is pinned, so the <select> can't snap to All");

// ── yes/no ───────────────────────────────────────────────────────────────────────
const yn = m.yesNoOptions([1, 2, 3], (x) => x > 1);
assert.deepEqual(yn.map((o) => o.label), ["Yes (2)", "No (1)"], "yes + no always sum to the rows");
assert.ok(m.matchesYesNo(true, "") && m.matchesYesNo(true, "yes") && !m.matchesYesNo(true, "no"));

// ── date ranges ───────────────────────────────────────────────────────────────────
assert.ok(m.inRange(null, m.EMPTY_RANGE), "an unset range constrains nothing, even a missing date");
assert.ok(!m.inRange(null, { preset: "today", from: "", to: "" }), "a set range excludes a missing date");

// ── at their defaults, the shared filters hide nothing ───────────────────────────
const plain = { society: null, created_at: null, assigned_at: null, meta_lead_id: null,
                phone: "+91 98765 43210", reject_reason: null, rejected_at: null };
assert.ok(m.passExtras(plain, m.EXTRA_DEFAULTS), "defaults filter nothing out");

// ── rejected stage: the three stages sharing the Rejected page ────────────────────
const fp = { ...plain, stage: "future_prospect" };
assert.ok(m.passExtras(fp, { ...m.EXTRA_DEFAULTS, rejStage: "future_prospect" }), "picks out a future prospect");
assert.ok(!m.passExtras(fp, { ...m.EXTRA_DEFAULTS, rejStage: "rnr" }), "and excludes it under RNR");
assert.deepEqual(
  m.rejectedStageOptions([{ stage: "rejected" }, { stage: "rnr" }, { stage: "rejected" }]).map((o) => o.label),
  ["Rejected (2)", "RNR (1)", "Future Prospect (0)"],
  "all three are always listed, a zero included — 'none yet' is still askable");

// ── source: multi-valued, a lead is found under every source it arrived from ───────
const both = { source: "meta", sources: ["meta", "99acres"] };
assert.ok(m.sourceMatches(both, "meta") && m.sourceMatches(both, "99acres"), "found under either source");
assert.ok(!m.sourceMatches(both, "whatsapp"), "and not under one it never came from");
assert.ok(m.sourceMatches(both, ""), "no selection constrains nothing");
assert.ok(m.sourceMatches({ source: "meta", sources: [] }, "meta"), "an unfilled sources column falls back to source");
assert.deepEqual(
  m.sourceOptions([both, { source: "meta", sources: ["meta"] }]).map((o) => o.label),
  ["Multiple sources (1)", "99acres (1)", "Meta (2)"],
  "each source counts every lead that has it; Multiple sources leads the list");
assert.ok(m.sourceMatches(both, m.MULTI_SOURCE), "two sources = multiple");
assert.ok(!m.sourceMatches({ source: "meta", sources: ["meta"] }, m.MULTI_SOURCE), "one source is not");
assert.ok(!m.sourceMatches({ source: "meta", sources: [] }, m.MULTI_SOURCE), "an unfilled column is one source");
assert.equal(m.sourceOptions([])[0].label, "Multiple sources (0)", "listed even when there are none");
assert.ok(m.sourceOptions([], "whatsapp").some((o) => o.value === "whatsapp"),
  "an active selection faceting dropped is pinned");

console.log("lead filters: ok");
