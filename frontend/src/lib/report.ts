/* Shared by the Reports table and the per-RM detail page.

   The date presets and the metric columns live here rather than on either page, so a
   column can't come to mean one thing in the summary and another in the drill-down —
   the two are read side by side and the numbers have to reconcile. */

const IST = "Asia/Kolkata";
const IST_OFFSET_MIN = 330;  // Asia/Kolkata, no DST

/* Every preset is computed on the IST calendar, not the browser's. An RM in another
   timezone — or one working past midnight IST — must see the same "Today" a manager
   in Delhi does, or the two of them read different numbers off the same button. */
export const istDay = (daysAgo = 0) =>
  new Date(Date.now() + IST_OFFSET_MIN * 60_000 - daysAgo * 864e5)
    .toISOString().slice(0, 10);

export const todayIST = () => istDay();

export type Preset = "all" | "today" | "yesterday" | "7d" | "15d" | "month" | "custom";

/* [from, to] per preset. `all` is resolved server-side from the log's own first row,
   so its bounds here are only a placeholder the response overwrites. */
export function rangeFor(p: Preset): [string, string] {
  const today = istDay();
  switch (p) {
    case "today":     return [today, today];
    case "yesterday": return [istDay(1), istDay(1)];
    // inclusive of today, so "Last 7 days" is 7 days of work, not 8
    case "7d":        return [istDay(6), today];
    case "15d":       return [istDay(14), today];
    case "month":     return [today.slice(0, 8) + "01", today];
    default:          return [today, today];
  }
}

export const PRESETS: { key: Preset; label: string }[] = [
  { key: "all",       label: "All" },
  { key: "today",     label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "7d",        label: "Last 7 days" },
  { key: "15d",       label: "Last 15 days" },
  { key: "month",     label: "This Month" },
  { key: "custom",    label: "Custom" },
];

/* Only the time — on the summary table the date is already the page's range, and in
   the drill-down it's already the row's own heading. */
export const hhmm = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString("en-IN",
    { timeZone: IST, hour: "2-digit", minute: "2-digit", hour12: false }) : null;

/* "Thu, 21 Aug 2026" for a bare YYYY-MM-DD. Parsed as UTC noon rather than local
   midnight: a bare date string is UTC in every browser, and midnight UTC is still the
   previous day in half the world's timezones — which would print the wrong weekday. */
export const dayLabel = (day: string) =>
  new Date(`${day}T12:00:00Z`).toLocaleDateString("en-IN",
    { timeZone: IST, weekday: "short", day: "numeric", month: "short", year: "numeric" });

export type MetricKey =
  | "calls_dialled" | "calls_connected" | "calls_missed"
  | "leads_qualified" | "visit_scheduled" | "revisit_booked" | "leads_rejected";

export const COLUMNS: { key: MetricKey; label: string; hint: string }[] = [
  { key: "calls_dialled",   label: "Dialled",   hint: "Connected + Missed, as marked by the RM" },
  { key: "calls_connected", label: "Connected", hint: "Marked 'Yes' on a call" },
  { key: "calls_missed",    label: "Missed",    hint: "Marked 'No', with a reason" },
  { key: "leads_qualified", label: "Qualified", hint: "Stage moved to qualified" },
  { key: "visit_scheduled", label: "Visit",     hint: "Stage moved to visit_scheduled" },
  { key: "revisit_booked",  label: "Revisit",   hint: "Stage moved to revisit_scheduled" },
  { key: "leads_rejected",  label: "Rejected",  hint: "Stage moved to rejected" },
];

/* Where the detail page for one RM lives. A helper because the link is built in two
   places and the querystring has to survive the round trip — the detail page reads
   its range back out of it. */
export const detailHref = (email: string, from: string, to: string, all: boolean) =>
  `/reports/detail?${new URLSearchParams(
    all ? { email, all: "true" } : { email, from, to })}`;
