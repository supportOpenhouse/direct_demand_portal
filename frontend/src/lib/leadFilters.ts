/* Filters every lead worklist shares — society, created date, assigned date, Meta
   form, invalid number — plus reject reason and rejected-on for the views that hold
   rejected leads (Home → Table and the Rejected page).

   One module, not four copies, for the reason lib/report.ts exists: a filter has to
   mean the same thing on every page, and a copy is exactly where two of them drift.
   A page takes three things from here: the defaults, one `passExtras` clause in its
   own `pass(l, skip)`, and the `extraFields` list. It keeps owning its own faceting,
   as FilterBar requires. */
import type { Lead } from "./api";
import { stageLabel } from "./leads";
import {
  NO_VALUE, countedOptions, inDatePreset, matchesOption,
  type DatePreset, type FilterOption,
} from "../components/Filters";
import type { Field, Values } from "../components/FilterBar";

export type DateRange = { preset: DatePreset; from: string; to: string };
export const EMPTY_RANGE: DateRange = { preset: "", from: "", to: "" };

/** A date range filter; an unset range (preset "") constrains nothing. */
export const inRange = (iso: string | null, r: DateRange | undefined) =>
  !r || !r.preset ? true : inDatePreset(iso, r.preset, r.from, r.to);

/* A number is valid when it is exactly 10 digits once a leading +91 is removed.
   Anything else — too short, too long, blank — is invalid.

   The +91 is stripped only when it is really there: a bare number that happens to
   START with 91 must not silently lose two digits and pass. Every number the sync
   could normalise is stored as "+91 xxxxx xxxxx", so in practice this flags exactly
   the rows `norm_phone` could not make into ten digits. */
export function isInvalidPhone(phone: string | null | undefined): boolean {
  const raw = (phone ?? "").trim();
  let digits = raw.replace(/\D/g, "");
  if (raw.startsWith("+91") && digits.startsWith("91")) digits = digits.slice(2);
  return digits.length !== 10;
}

/* A lead "has a Meta form" when a Meta webhook delivery reached it. `meta_lead_id` is
   stamped on the first such delivery and never cleared, so it answers "did a form ever
   arrive" — which is the question. (It is NOT the join key for the form itself; the
   popup's form card joins on origin_key, for repeat submissions.) Leads that came in
   through the Meta SHEET have no form record, and correctly read No. */
export const hasMetaForm = (l: Pick<Lead, "meta_lead_id">) => !!l.meta_lead_id;

export const YES = "yes";
export const NO = "no";

/** Yes/No with live counts that always sum to the rows in view. */
export function yesNoOptions<T>(items: T[], test: (i: T) => boolean): FilterOption[] {
  let yes = 0;
  for (const it of items) if (test(it)) yes += 1;
  return [
    { value: YES, label: `Yes (${yes})` },
    { value: NO, label: `No (${items.length - yes})` },
  ];
}

export const matchesYesNo = (v: boolean, sel: string) => !sel || (sel === YES ? v : !v);

/** Case-insensitive, because leads carry the society as typed into a sheet and the
    master table has its own spelling. NO_VALUE = no society on the lead. */
export function societyMatches(society: string | null | undefined, sel: string): boolean {
  if (!sel) return true;
  const v = (society ?? "").trim();
  if (sel === NO_VALUE) return !v;
  return v.toLowerCase() === sel.trim().toLowerCase();
}

/* The option list is master_societies — so a society with no leads in view is still
   askable, the same reasoning as rmOptions. Two additions keep every lead reachable:
     * a society on a lead that is NOT in the master table (a typo, or a project the
       table hasn't got yet) is appended, or those leads could never be filtered to;
     * "— None —" for leads with no society at all.
   Master spelling wins where both exist. Sorted alphabetically so a native <select>'s
   type-ahead can jump through ~1,160 names. */
export function societyOptions<T>(
  items: T[], get: (i: T) => string | null | undefined, master: string[], keep = "",
): FilterOption[] {
  const counts = new Map<string, number>();
  const leadSpelling = new Map<string, string>();
  let none = 0;
  for (const it of items) {
    const v = (get(it) ?? "").trim();
    if (!v) { none += 1; continue; }
    const k = v.toLowerCase();
    counts.set(k, (counts.get(k) ?? 0) + 1);
    if (!leadSpelling.has(k)) leadSpelling.set(k, v);
  }
  const names = new Map<string, string>();
  for (const m of master) {
    const t = m.trim();
    if (t) names.set(t.toLowerCase(), t);
  }
  for (const [k, v] of leadSpelling) if (!names.has(k)) names.set(k, v);

  const opts: FilterOption[] = [...names.entries()]
    .sort((a, b) => a[1].localeCompare(b[1]))
    .map(([k, label]) => ({ value: label, label: `${label} (${counts.get(k) ?? 0})` }));
  if (none > 0) opts.push({ value: NO_VALUE, label: `— None — (${none})` });
  // pin a selection faceting dropped, so the <select> can't silently snap to "All"
  if (keep && !opts.some((o) => typeof o !== "string" && o.value === keep)) {
    opts.push({ value: keep, label: keep === NO_VALUE ? "— None — (0)" : `${keep} (0)` });
  }
  return opts;
}

/* The three stages that share the Rejected page: rejected itself, plus rnr and
   future_prospect, which have no page of their own. Listed ALWAYS, zeros included —
   "Future Prospect (0)" is the answer to "do we have any?", and a filter that dropped
   the option exactly when the answer is none could not be asked. Labels come from
   stageLabel, so the option reads the same as the chip on the row. */
export const REJECTED_STAGES = ["rejected", "rnr", "future_prospect"] as const;

export function rejectedStageOptions<T extends { stage: string }>(items: T[]): FilterOption[] {
  const n: Record<string, number> = {};
  for (const it of items) n[it.stage] = (n[it.stage] ?? 0) + 1;
  return REJECTED_STAGES.map((s) => ({ value: s, label: `${stageLabel(s)} (${n[s] ?? 0})` }));
}

export const EXTRA_DEFAULTS = {
  society: "",
  created: EMPTY_RANGE,
  assigned: EMPTY_RANGE,
  metaForm: "",
  badPhone: "",
  rejStage: "",
  rejectReason: "",
  rejectedOn: EMPTY_RANGE,
};

/** The shared clauses for a page's `pass(l, skip)`. A hidden field keeps its default,
    so the reject clauses constrain nothing on pages that don't show them. */
export function passExtras(l: Lead, f: Values, skip?: string): boolean {
  return (skip === "society" || societyMatches(l.society, f.society)) &&
    (skip === "created" || inRange(l.created_at, f.created)) &&
    (skip === "assigned" || inRange(l.assigned_at, f.assigned)) &&
    (skip === "metaForm" || matchesYesNo(hasMetaForm(l), f.metaForm)) &&
    (skip === "badPhone" || matchesYesNo(isInvalidPhone(l.phone), f.badPhone)) &&
    (skip === "rejStage" || !f.rejStage || l.stage === f.rejStage) &&
    (skip === "rejectReason" || matchesOption(l.reject_reason, f.rejectReason)) &&
    (skip === "rejectedOn" || inRange(l.rejected_at, f.rejectedOn));
}

/** The shared fields, counted against each field's own `pass(l, <key>)` so the
    counts stay live, exactly like the page's existing fields. */
export function extraFields<L extends Lead>(
  all: L[], pass: (l: L, skip?: string) => boolean, f: Values, master: string[],
  opts: { rejected: boolean },
): Field[] {
  return [
    { key: "society", label: "Society",
      options: societyOptions(all.filter((l) => pass(l, "society")), (l) => l.society, master, f.society) },
    { key: "created", label: "Created", kind: "daterange" },
    { key: "assigned", label: "Assigned", kind: "daterange" },
    { key: "metaForm", label: "Meta form",
      options: yesNoOptions(all.filter((l) => pass(l, "metaForm")), hasMetaForm) },
    { key: "badPhone", label: "Invalid number",
      options: yesNoOptions(all.filter((l) => pass(l, "badPhone")), (l) => isInvalidPhone(l.phone)) },
    // first of the reject filters: it's the split people reach for before the reason
    { key: "rejStage", label: "Rejected stage", hidden: !opts.rejected,
      options: rejectedStageOptions(all.filter((l) => pass(l, "rejStage"))) },
    { key: "rejectReason", label: "Reject reason", hidden: !opts.rejected,
      options: countedOptions(all.filter((l) => pass(l, "rejectReason")), (l) => l.reject_reason,
                              "No reason", (v) => v, f.rejectReason) },
    { key: "rejectedOn", label: "Rejected on", kind: "daterange", hidden: !opts.rejected },
  ];
}
