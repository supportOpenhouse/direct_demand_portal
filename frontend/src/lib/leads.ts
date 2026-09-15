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
};
const SRC_LABEL: Record<string, string> = {
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
   is never in two lists or none. rnr and future_prospect have no page of their own;
   both live on Rejected, badged. */
const STAGE_LABEL: Record<string, string> = {
  new: "New",
  call_not_received: "Call Not Received",
  follow_up: "Call Back Again",
  qualified: "Qualified",
  visit_scheduled: "Visit Scheduled",
  revisit_scheduled: "Revisit Scheduled",
  won: "Won",
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

export function isNewToday(l: { received_at?: string | null; assigned_at?: string | null }): boolean {
  const t = todayIST();
  return (!!l.received_at && istDayOf(l.received_at) === t)
      || (!!l.assigned_at && istDayOf(l.assigned_at) === t);
}

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
  pipeline: "--amber",
  // Visit and Revisit share the `visit` stage class everywhere else, which renders
  // two identical bars side by side here — gold keeps them apart without leaving
  // the warm end of the ramp they both belong to.
  revisit: "--gold",
  converted: "--emerald",
  rejected: "--coral",
  // Not a segment — future prospects live inside "rejected" — but the funnel draws
  // it as a bar of its own, and this map must stay the ONE place a stage's colour is
  // decided. Same token as the stage chip, so the bar and the chip agree.
  future_prospect: "--prospect",
};

/** CSS var for a segment's colour; `null` (the ALL bucket) is the brand. */
export const segHue = (seg: string | null) =>
  seg === null ? "var(--brand)" : `var(${SEG_HUE[seg] ?? "--slate"})`;

export const ALL_STAGES = [
  "new", "call_not_received", "follow_up", "qualified",
  "visit_scheduled", "revisit_scheduled", "won", "future_prospect", "rejected", "rnr",
] as const;

const STAGE_CLASS: Record<string, string> = {
  new: "new",
  call_not_received: "contacted",
  follow_up: "planned",
  qualified: "nego",
  visit_scheduled: "visit",
  revisit_scheduled: "visit",
  won: "won",
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
  { seg: "call_not_received", route: "/leads/call-not-received", label: "Call Not Received" },
  { seg: "followup", route: "/leads/followup", label: "Call Back Again" },
  { seg: "qualified", route: "/leads/qualified", label: "Qualified" },
  // "pipeline" segment = stage visit_scheduled, shown as "Visited"; a revisit booking
  // advances the lead to the new "revisit" segment, shown as "Pipeline"
  { seg: "pipeline", route: "/leads/pipeline", label: "Visited" },
  { seg: "revisit", route: "/leads/revisit", label: "Pipeline" },
  { seg: "converted", route: "/leads/converted", label: "Converted" },
  // RNR and Future Prospect leads keep their own stage but live on the Rejected page, badged
  { seg: "rejected", route: "/leads/rejected", label: "Rejected" },
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
