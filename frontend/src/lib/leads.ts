/* Source + plan-to-buy display helpers, matching the prototype's .src / .plan-chip classes. */

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
