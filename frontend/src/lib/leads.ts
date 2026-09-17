/* Cities we operate in. Shared because both create-lead forms (WhatsApp chat and
   the Huvo call log) offer it — two copies would drift into offering different
   cities on different pages. */
export const CITIES = ["Ghaziabad", "Noida", "Gurgaon"];

/* Source + plan-to-buy display helpers, matching the prototype's .src / .plan-chip classes. */
import { matches } from "../components/SearchContext";
import type { Lead } from "./api";

// source value (from backend) → CSS class key used by .src.<key> in app.css
const SRC_CLASS: Record<string, string> = {
  meta: "meta",
  "99acres": "acres",
  magicbricks: "bricks",
  gads: "gads",
  youtube: "yt",
  whatsapp: "wa",
  manual: "manual",
};
const SRC_LABEL: Record<string, string> = {
  manual: "Manual",   // added by hand from the topbar
  meta: "Meta",
  "99acres": "99acres",
  magicbricks: "MagicBricks",
  gads: "Google Ads",
  youtube: "YouTube",
  whatsapp: "WhatsApp",
};

export const srcClass = (s: string) => SRC_CLASS[s] || "meta";
export const srcLabel = (s: string) => SRC_LABEL[s] || s;

/** Every source the buyer arrived from, first one first. Falls back to `source` for a
    lead whose `sources` column hasn't been filled. */
export const leadSources = (l: Pick<Lead, "source" | "sources">): string[] =>
  l.sources?.length ? l.sources : [l.source];
/** "Meta, 99acres" — for sorting, search and CSV. */
export const sourcesLabel = (l: Pick<Lead, "source" | "sources">) =>
  leadSources(l).map(srcLabel).join(", ");

/* Meta's Instant Form field keys are machine names ("your_budget_range?",
   "where_do_you_currently_live?"). The form asked them in words, so show words.
   Shared by the Meta Leads page and the lead popup's captured-from-Meta card — the
   same question must not read two ways on two screens. */
export const metaQuestionLabel = (name: string): string => {
  const s = name.replace(/_/g, " ").replace(/\s+/g, " ").trim();
  return s ? s[0].toUpperCase() + s.slice(1) : name;
};

// plan-to-buy value → .plan-chip modifier (colour ramp from the prototype)
const PLAN_CLASS: Record<string, string> = {
  "Within 30 days": "plan-hot",
  "1–3 months": "plan-warm",
  "3–6 months": "plan-cool",
  "Just exploring": "plan-cold",
  "6+ months": "plan-cold",
};
export const planClass = (p: string) => PLAN_CLASS[p] || "plan-cool";

export const initials = (n: string | null) =>
  (n || "?")
    .split(" ")
    .map((x) => x[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

/* Every stage. `stage` is authoritative — each maps to exactly one page, so a lead
   is never in two lists or none. Three pages hold two stages each: Call Not Received
   (+ rnr), Visited Leads (visit_scheduled + revisit_scheduled), and — until 16 Sep —
   Rejected. future_prospect has its own page now. */
const STAGE_LABEL: Record<string, string> = {
  new: "New",
  call_not_received: "Call Not Received",
  follow_up: "Call Back Again",
  qualified: "Qualified",
  visit_scheduled: "Visit Scheduled",
  revisit_scheduled: "Revisit Scheduled",
  converted: "Converted",
  future_prospect: "Future Prospect",
  rejected: "Rejected",
  rnr: "RNR",
};
/* Every stage a lead can hold, in funnel order. Mirrors the backend's STAGES
   tuple in routers/leads.py — the manual stage setter validates against that, so
   a value here that is missing there is a 422 the user cannot explain. */
/* The starburst NEW badge: this lead ARRIVED or was ASSIGNED today.

   On the IST calendar, not the browser's — a UTC boundary rolls the day at 05:30
   IST, mid-shift, so an RM abroad would see a different "today" than Delhi does.

   Assigned counts as well as received: a lead handed to you this morning is new TO
   YOU even if it came in last week, and that is the row you want marked. */
const IST_OFFSET_MIN = 330;
const istDayOf = (iso: string) =>
  new Date(new Date(iso).getTime() + IST_OFFSET_MIN * 60_000).toISOString().slice(0, 10);
const todayIST = () =>
  new Date(Date.now() + IST_OFFSET_MIN * 60_000).toISOString().slice(0, 10);

export function isNewToday(l: {
  received_at?: string | null; assigned_at?: string | null;
  stage?: string; stage_changed_at?: string | null;
}): boolean {
  const t = todayIST();
  return (!!l.received_at && istDayOf(l.received_at) === t)
      || (!!l.assigned_at && istDayOf(l.assigned_at) === t)
      // moved into its CURRENT stage today — any stage: a lead that reached Qualified this
      // morning is new to the Qualified list, and a repeat arrival reset to New keeps its
      // old received_at, so without this both would read as stale leads
      || (!!l.stage_changed_at && istDayOf(l.stage_changed_at) === t);
}

/** Rows carrying the NEW badge first, the rest after. Each group keeps the order it
    arrived in — the page's own sort — so a column sort still applies within both. */
export const newFirst = <T extends Parameters<typeof isNewToday>[0]>(rows: T[]): T[] =>
  [...rows.filter((r) => isNewToday(r)), ...rows.filter((r) => !isNewToday(r))];

/* A SEGMENT's colour token — the one used by the stage filter boxes on Home →
   Table and by the funnel bars, so the two can never disagree about what colour
   "Qualified" is.

   Keyed by segment (the page a lead lives on) rather than by stage, because that
   is what both call sites actually hold. */
const SEG_HUE: Record<string, string> = {
  new: "--blue",
  call_not_received: "--cyan",
  followup: "--slate",
  qualified: "--indigo",
  // its own page since 16 Sep; same token as the stage chip, so the bar, the box and
  // the chip all agree — this map stays the ONE place a segment's colour is decided
  future_prospect: "--prospect",
  // one page for visit_scheduled + revisit_scheduled. The gold that used to separate
  // Revisit from Visit is unused now that they share a page.
  visited: "--amber",
  rejected: "--coral",
  converted: "--emerald",
};

/** CSS var for a segment's colour; `null` (the ALL bucket) is the brand. */
export const segHue = (seg: string | null) =>
  seg === null ? "var(--brand)" : `var(${SEG_HUE[seg] ?? "--slate"})`;

export const ALL_STAGES = [
  "new", "call_not_received", "follow_up", "qualified",
  "visit_scheduled", "revisit_scheduled", "converted", "future_prospect", "rejected", "rnr",
] as const;

const STAGE_CLASS: Record<string, string> = {
  new: "new",
  call_not_received: "contacted",
  follow_up: "planned",
  qualified: "nego",
  visit_scheduled: "visit",
  revisit_scheduled: "visit",
  // the CSS class stays `won` — it is the emerald chip, and VisitsCell reuses it for a
  // COMPLETED VISIT, which has nothing to do with the lead stage that was renamed
  converted: "won",
  // Its own hue, NOT `lost`: it shares the Rejected page with genuinely dead leads,
  // and a parked buyer drawn in the same coral would be indistinguishable from one.
  future_prospect: "prospect",
  rejected: "lost",
  rnr: "lost",
};
export const stageLabel = (s: string) => STAGE_LABEL[s] || s;
export const stageClass = (s: string) => STAGE_CLASS[s] || "new";

/* Every lead worklist, in funnel order. A lead lives in exactly one of these
   segments, and each maps 1:1 to a tab/route — used by the global search to say
   which tab a matched lead is in and to navigate there. */
export const LEAD_SEGMENTS: { seg: string; route: string; label: string }[] = [
  { seg: "new", route: "/leads/new", label: "New Leads" },
  // rnr (10 straight misses, never reached) is the same problem further along, so it
  // sits with the leads still being chased rather than under Rejected
  { seg: "call_not_received", route: "/leads/call-not-received", label: "Call Not Received" },
  { seg: "followup", route: "/leads/followup", label: "Call Back Again" },
  { seg: "qualified", route: "/leads/qualified", label: "Qualified Leads" },
  { seg: "future_prospect", route: "/leads/future-prospect", label: "Future Prospect" },
  // visit_scheduled + revisit_scheduled. A revisit is the same buyer returning to the
  // same property — a stronger signal, but not different work, so one page holds both.
  { seg: "visited", route: "/leads/visited", label: "Visited Leads" },
  { seg: "rejected", route: "/leads/rejected", label: "Rejected" },
  { seg: "converted", route: "/leads/converted", label: "Converted" },
];

/* Single source of truth for "does this lead match the search box" — every lead
   list AND the global search use it, so a hit in the dropdown is guaranteed to
   still match once we land on its tab. Covers all human-meaningful fields; phone
   also matches digits-only so "9560068322" finds "+91 95600 68322". */
export function leadMatchesQuery(query: string, l: Lead): boolean {
  if (
    matches(
      query,
      l.name, l.phone, l.email, l.city, l.society, l.configuration,
      l.budget_band, l.plan_to_buy, l.assigned_to, l.latest_note, l.source_remarks,
      sourcesLabel(l), stageLabel(l.stage),
    )
  )
    return true;
  const qDigits = query.replace(/\D/g, "");
  return qDigits.length >= 3 && !!l.phone && l.phone.replace(/\D/g, "").includes(qDigits);
}
