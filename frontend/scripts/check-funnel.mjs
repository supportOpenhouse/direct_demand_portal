#!/usr/bin/env node
/* The funnel's rules, which are the non-obvious parts:
     1. every bar is its OWN count — nothing cumulative;
     2. "All" is the whole lead book, so it is always the largest;
     3. All fills its track; the TRACK is half the card (CSS), leaving the right
        half for the count, the share and the range filter;
     4. New, Call Not Received, Call Back Again and Rejected are not bars — they sit
        in the side band, and bars + band add up to All;
     5. Future Prospect is drawn below Closed but is NOT a step — it may outnumber
        Closed, so the narrowing rule stops at Closed. */
import assert from "node:assert/strict";

const STAGES = [
  { seg: null, label: "All" }, { seg: "qualified", label: "Qualified" },
  { seg: "pipeline", label: "Visit" }, { seg: "revisit", label: "Revisit" },
  { seg: "converted", label: "Closed" },
  { seg: "future_prospect", label: "Future Prospect" },
];
const FLOW = 5;   // All → Closed; the rows after this are outside the flow
/* Widths are now a fraction of the TRACK, and the track itself is half the card —
   so a full bar is 1.0 here, not 0.5. */
const MIN_W = 0.04;
const curve = (share) => Math.sqrt(share);

function funnelGeometry(by, total) {
  const counts = STAGES.map((s) => (s.seg === null ? total : by[s.seg] ?? 0));
  const share = counts.map((c) => (total ? c / total : 0));
  const widths = counts.map((c, i) => (c === 0 ? 0 : Math.max(MIN_W, curve(share[i]))));
  return { counts, share, widths, total };
}

// future_prospect is also inside `rejected` (278) — the funnel counts it twice on
// purpose: once in its segment, once on its own bar. `total` counts each lead once.
const by = { new: 2500, rejected: 278, qualified: 468, pipeline: 97, revisit: 4, converted: 0,
             future_prospect: 12 };
const g = funnelGeometry(by, 3347);

assert.deepEqual(g.counts, [3347, 468, 97, 4, 0, 12], "each bar is its own count");
assert.equal(g.share[0], 1, "All is the whole book, so 100%");
assert.equal(g.widths[0], 1, "All fills its track completely");
assert.ok(g.widths.every((w) => w <= 1), "nothing overflows the track");
// Rejected and New are folded into All, never drawn on their own.
assert.ok(!g.counts.includes(278) && !g.counts.includes(2500), "rejected/new are not bars");
// Order must survive the scale, and the steps must stay visible.
g.widths.slice(0, FLOW).forEach((w, i) => i && assert.ok(w <= g.widths[i - 1], "the flow must narrow"));
// ...and only the flow. A parked bucket outnumbering Closed is normal, not a bug.
assert.ok(g.widths[FLOW] > g.widths[FLOW - 1], "Future Prospect may be wider than Closed");
assert.ok(g.counts[FLOW] < g.counts[0], "Future Prospect is still a slice of All");
// >= not >: a 4-lead stage computes to 1.7% and CLAMPS to the 2% floor, which is
// exactly what the floor is for. Asserting > here failed on correct behaviour.
g.widths.slice(0, 4).forEach((w) => assert.ok(w >= MIN_W, "a non-empty bar is visible"));
// "none" and "almost none" must not look the same.
assert.equal(g.widths[FLOW - 1], 0, "an empty stage draws nothing");
assert.ok(g.widths[3] >= MIN_W, "a stage with 4 leads still draws");
// No leads at all must not divide by zero.
assert.ok(funnelGeometry({}, 0).widths.every((w) => w === 0), "zero total is safe");

// --- other stages (the side band) --------------------------------------------
// Replaced the step conversions 14 Sep: bars are CURRENT counts, not cumulative, so
// "Visit / Qualified" could print 400%. Mirrors otherStages() in LeadFunnel.tsx.
const OTHER = [
  { seg: "new", label: "New Leads" }, { seg: "call_not_received", label: "Call Not Received" },
  { seg: "followup", label: "Call Back Again" }, { seg: "rejected", label: "Rejected" },
];
function otherStages(b) {
  return OTHER.map((o) => ({ ...o, count: o.seg === "rejected"
    ? (b.rejected ?? 0) - (b.future_prospect ?? 0) : b[o.seg] ?? 0 }));
}
const o = otherStages(by);
assert.deepEqual(o.map((x) => x.count), [2500, 0, 0, 266], "band counts, missing segments are 0");
assert.equal(o[3].count, 278 - 12, "Rejected excludes future prospects — they already have a bar");
// The property that makes the card honest: nothing counted twice, nothing dropped.
const bars = g.counts.slice(1).reduce((n, c) => n + c, 0);
const band = o.reduce((n, x) => n + x.count, 0);
assert.equal(bars + band, g.total, "bars + side band = All");
assert.ok(OTHER.every((x) => !STAGES.some((st) => st.seg === x.seg)), "no stage is both a bar and in the band");

console.log("funnel geometry: ok");
for (const x of o) console.log(`  ${x.label.padEnd(18)} ${String(x.count).padStart(5)}`);
for (const [i, s] of STAGES.entries())
  console.log(`  ${s.label.padEnd(10)} count ${String(g.counts[i]).padStart(5)}   ${(g.share[i] * 100).toFixed(1).padStart(5)}%   bar ${(g.widths[i] * 100).toFixed(1).padStart(5)}% of track`);
