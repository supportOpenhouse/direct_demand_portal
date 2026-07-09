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

// our backend stage keys → prototype label + .stage.<class>
const STAGE_LABEL: Record<string, string> = {
  new: "New", contacted: "Contacted", visit_scheduled: "Visit Scheduled",
  visit_feedback: "Visit Feedback", negotiation: "Negotiation", won: "Won",
  lost: "Lost", rejected: "Rejected", future_prospect: "Future Prospect", timepass: "Timepass",
};
const STAGE_CLASS: Record<string, string> = {
  new: "new", contacted: "contacted", visit_scheduled: "visit", visit_feedback: "feedback",
  negotiation: "nego", won: "won", lost: "lost", rejected: "lost", future_prospect: "future", timepass: "timepass",
};
export const stageLabel = (s: string) => STAGE_LABEL[s] || s;
export const stageClass = (s: string) => STAGE_CLASS[s] || "new";

/* Every lead worklist, in funnel order. A lead lives in exactly one of these
   segments, and each maps 1:1 to a tab/route — used by the global search to say
   which tab a matched lead is in and to navigate there. */
export const LEAD_SEGMENTS: { seg: string; route: string; label: string }[] = [
  { seg: "new", route: "/leads/new", label: "New Leads" },
  { seg: "followup", route: "/leads/followup", label: "Follow-up" },
  { seg: "qualified", route: "/leads/qualified", label: "Qualified" },
  { seg: "pipeline", route: "/leads/pipeline", label: "Pipeline" },
  { seg: "converted", route: "/leads/converted", label: "Converted" },
  { seg: "rnr", route: "/leads/rnr", label: "RNR" },
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
      srcLabel(l.source), stageLabel(l.stage),
    )
  )
    return true;
  const qDigits = query.replace(/\D/g, "");
  return qDigits.length >= 3 && !!l.phone && l.phone.replace(/\D/g, "").includes(qDigits);
}
