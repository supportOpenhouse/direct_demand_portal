/* Lead funnel across the top of Summary.

   Every bar is its OWN count -- nothing cumulative. "All" is the whole lead book
   for the chosen range, so it is the largest by definition and the four stages
   read as slices of it.

   New, Call Not Received, Call Back Again and Rejected are not drawn as bars:
   nothing flows forward out of Rejected, and the other three have not entered the
   funnel yet. Their counts sit in the band on the right instead, so bars + band add
   up to All.

   Future Prospect IS drawn, below Closed and set apart from the steps above it. It
   is not a step — a parked buyer did not "come after" Closed — so it sits outside
   the narrowing flow and has no conversion ratio. It is counted by STAGE, not by
   segment: future prospects live inside the Rejected segment, so a segment count
   would never see them.

   Counts come from `useAllLeads` -- the same react-query cache the lists and the
   Table view's stage boxes read, so the funnel can never disagree with them. */
import { useMemo, useState } from "react";
import { useAllLeads, useAssignees } from "../lib/queries";
import { useAuth } from "./AuthContext";
import { matchesOption, rmOptions } from "./Filters";
import { segHue } from "../lib/leads";
import { istDay, todayIST } from "../lib/report";
import { Skeleton } from "./Skeleton";

export const STAGES: { seg: string | null; label: string }[] = [
  { seg: null,        label: "All" },
  { seg: "qualified", label: "Qualified" },
  { seg: "pipeline",  label: "Visit" },
  { seg: "revisit",   label: "Revisit" },
  { seg: "converted", label: "Closed" },
  { seg: "future_prospect", label: "Future Prospect" },
];

type Range = "week" | "month" | "all" | "custom";
const RANGES: { v: Range; label: string }[] = [
  { v: "week",   label: "This week" },
  { v: "month",  label: "This month" },
  { v: "all",    label: "All time" },
  { v: "custom", label: "Custom" },
];

/* A non-zero stage never disappears; an empty one draws nothing, because "0" and
   "almost none" must not look the same. */
const MIN_W = 0.04;

/* Width is the SQUARE ROOT of the share.

   The book spans orders of magnitude -- 4,044 leads down to 4 revisits is 0.1% --
   and on a linear scale everything below the first bar is a sub-pixel sliver. sqrt
   keeps the order exact and the steps visible. The count and the TRUE percentage
   sit beside every bar, so the figure itself is never what gets compressed. */
const curve = (share: number) => Math.sqrt(share);

/** Counts, shares and widths as a fraction of the track. Pure, so it can be checked
    without rendering: `node scripts/check-funnel.mjs`. */
export function funnelGeometry(by: Record<string, number>, total: number) {
  const counts = STAGES.map((s) => (s.seg === null ? total : by[s.seg] ?? 0));
  const share = counts.map((c) => (total ? c / total : 0));
  const widths = counts.map((c, i) => (c === 0 ? 0 : Math.max(MIN_W, curve(share[i]))));
  return { counts, share, widths, total };
}

/* IST calendar, not the browser's: a UTC boundary rolls the day at 05:30 IST,
   mid-shift, so an RM abroad would see a different "this week" than Delhi does. */
const IST_OFFSET_MIN = 330;
const istDayOf = (iso: string) =>
  new Date(new Date(iso).getTime() + IST_OFFSET_MIN * 60_000).toISOString().slice(0, 10);

/** Monday-start week, on the IST calendar. */
function weekStartIST(): string {
  const today = todayIST();
  const dow = (new Date(today + "T00:00:00Z").getUTCDay() + 6) % 7;   // Mon = 0
  return istDay(dow);
}

/* The stages the bars don't draw, for the band on the right.

   This band used to hold step conversions (Visit / Qualified …). They were removed
   14 Sep as misleading: every bar is its OWN current count, not the cumulative number
   that ever reached the stage, so a lead that moved on from Qualified to Visit no
   longer counts as Qualified — and "Visit / Qualified" printed 400%.

   Rejected EXCLUDES future prospects: they live in the rejected segment but already
   have a bar, and counting them twice would break "bars + band = All". RNR stays in
   Rejected, which is the page it lives on. */
const OTHER_STAGES: { seg: string; label: string }[] = [
  { seg: "new",               label: "New Leads" },
  { seg: "call_not_received", label: "Call Not Received" },
  { seg: "followup",          label: "Call Back Again" },
  { seg: "rejected",          label: "Rejected" },
];

export function otherStages(by: Record<string, number>) {
  return OTHER_STAGES.map((s) => ({
    ...s,
    count: s.seg === "rejected"
      ? (by.rejected ?? 0) - (by.future_prospect ?? 0)
      : by[s.seg] ?? 0,
  }));
}

export function LeadFunnel() {
  const { leads, isLoading } = useAllLeads(true);
  const [range, setRange] = useState<Range>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  /* RM filter, admins only. An RM's lead set is already scoped to their own leads by
     the server (`_role_scope`), so for them the dropdown could only ever offer one
     name. Same `rmOptions`/`matchesOption` pair as every list page: every assignable
     RM is offered with their count — including 0 — plus Unassigned. */
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  const assignees = useAssignees();
  const [rm, setRm] = useState("");

  const bounds = useMemo((): [string, string] | null => {
    if (range === "all") return null;
    if (range === "custom") return from || to ? [from || "0000-01-01", to || "9999-12-31"] : null;
    if (range === "week") return [weekStartIST(), todayIST()];
    return [todayIST().slice(0, 8) + "01", todayIST()];              // this month
  }, [range, from, to]);

  /* Leads in the chosen range, BEFORE the RM filter — the dropdown counts are taken
     from this, so each name shows what picking it would give rather than 0 for
     everyone but the current pick. */
  const inRange = useMemo(() => leads.filter((r) => {
    if (r.lead.is_test) return false;
    if (!bounds) return true;
    // No received_at means we cannot place the lead in time, so a dated range
    // must exclude it rather than silently counting it in every window.
    if (!r.lead.received_at) return false;
    const d = istDayOf(r.lead.received_at);
    return d >= bounds[0] && d <= bounds[1];
  }), [leads, bounds]);

  const rmOpts = useMemo(
    () => rmOptions(inRange, (r) => r.lead.assigned_to,
                    (assignees.data?.items ?? []).map((a) => a.name), rm),
    [inRange, assignees.data, rm],
  );

  const { counts, share, widths, total, others } = useMemo(() => {
    const by: Record<string, number> = {};
    let n = 0;
    for (const r of inRange) {
      if (!matchesOption(r.lead.assigned_to, rm)) continue;
      by[r.segment.seg] = (by[r.segment.seg] ?? 0) + 1;
      // Also counted on its own: its segment is "rejected", which the funnel doesn't
      // draw, so this is the only way the bar can see it. It stays in `n` exactly
      // once, as every lead does.
      if (r.lead.stage === "future_prospect")
        by.future_prospect = (by.future_prospect ?? 0) + 1;
      n += 1;
    }
    return { ...funnelGeometry(by, n), others: otherStages(by) };
  }, [inRange, rm]);

  return (
    <div className="card panel-pad fn-card">
      <div className="fn-head">
        <div className="fn-title">Lead funnel</div>
        <div className="fn-controls">
          {isAdmin && (
            <select className="ctl fn-rm" value={rm} onChange={(e) => setRm(e.target.value)}
                    title="Assigned RM">
              <option value="">All RMs</option>
              {rmOpts.map((o) => typeof o === "string"
                ? <option key={o} value={o}>{o}</option>
                : <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          )}
          <div className="fn-ranges">
            {RANGES.map((r) => (
              <button key={r.v} className={"btn sm" + (range === r.v ? "" : " ghost")}
                      onClick={() => setRange(r.v)}>{r.label}</button>
            ))}
          </div>
          {range === "custom" && (
            <div className="fn-custom">
              <input type="date" className="ctl" value={from} onChange={(e) => setFrom(e.target.value)} title="From (IST)" />
              <span>–</span>
              <input type="date" className="ctl" value={to} onChange={(e) => setTo(e.target.value)} title="To (IST)" />
            </div>
          )}
          <div className="fn-total">
            <span>Total:</span>
            {isLoading ? <Skeleton w={68} h={18} /> : <b>{total.toLocaleString("en-IN")}</b>}
          </div>
        </div>
      </div>

      <div className="fn-body">
      <div className="fn-rows">
        {STAGES.map((s, i) => (
          <div className={"fn-row" + (s.seg === "future_prospect" ? " fn-aside" : "")} key={s.label}>
            <span className="fn-label">{s.label}</span>
            <div className="fn-track">
              {/* Each bar carries its own stage colour, the same one the stage
                  filter boxes use — `segHue` is the single map, so the two views
                  can never disagree about what "Qualified" looks like. */}
              <div className="fn-fill"
                   style={{ width: `${widths[i] * 100}%`, background: segHue(s.seg) }} />
            </div>
            <div className="fn-nums">
              {isLoading ? <Skeleton w={44} h={13} /> : <b>{counts[i].toLocaleString("en-IN")}</b>}
              <span>{isLoading ? "—" : `${(share[i] * 100).toFixed(1)}%`}</span>
            </div>
          </div>
        ))}
      </div>

      {/* The right-hand band the bars leave empty — the stages they don't draw,
          coloured like their stage boxes (`segHue`, the one map). */}
      <aside className="fn-others">
        <div className="fn-others-head">Other stages</div>
        {others.map((o) => (
          <div className="fn-other" key={o.seg}>
            <b style={{ color: segHue(o.seg) }}>
              {isLoading ? "—" : o.count.toLocaleString("en-IN")}
            </b>
            <span>{o.label}</span>
          </div>
        ))}
      </aside>
      </div>
    </div>
  );
}
