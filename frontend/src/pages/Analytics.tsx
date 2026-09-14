/* Analytics — measurable lead & supply parameters, computed client-side from the
   full lead set (all segments) + the supply pipeline. Opened from Home's
   Analytics toggle; the existing overview is left untouched. No backend changes:
   everything here is derived from data the app already loads.

   Definitions are labelled inline so every number is unambiguous. `new Date()` is
   fine here (browser runtime). Test leads (is_test) are excluded throughout. */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell } from "recharts";
import { useAllLeads } from "../lib/queries";
import { useAuth } from "../components/AuthContext";
import { srcLabel } from "../lib/leads";
import { Lead, api } from "../lib/api";
import { IconChart, IconTrend, IconMegaphone, IconCity, IconChevronRight } from "../components/icons";
import { LeadFunnel } from "../components/LeadFunnel";

const SOURCE_COLOR: Record<string, string> = { meta: "var(--blue)", "99acres": "var(--supply-orange)", magicbricks: "var(--coral)" };
const sourceColor = (s: string) => SOURCE_COLOR[s] || "var(--slate)";
// categorical palette for the city donut (assigned in byCity order, fixed)
const CITY_COLORS = ["var(--indigo)", "var(--cyan)", "var(--amber)", "var(--coral)", "var(--emerald)", "var(--violet)", "var(--cyan)", "var(--slate)"];
const TREND_RANGES: { v: number | "all"; label: string }[] = [
  { v: 7, label: "7d" }, { v: 15, label: "15d" }, { v: 30, label: "30d" }, { v: "all", label: "All" },
];
const card = { background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "var(--radius)", boxShadow: "var(--shadow)" } as const;
const HOT_PLAN = "Within 30 days";

// My performance: the stage chips, one per lead segment, in funnel order (matches the tabs)
const STAGE_COLS: { seg: string; label: string }[] = [
  { seg: "new", label: "New Leads" },
  { seg: "call_not_received", label: "Call Not Received" },
  { seg: "followup", label: "Call Back Again" },
  { seg: "qualified", label: "Qualified Leads" },
  { seg: "pipeline", label: "Visited Leads" },
  { seg: "revisit", label: "Pipeline Leads" },
  { seg: "converted", label: "Converted Leads" },
  { seg: "rejected", label: "Rejected Leads" },
];
const REP_RANGES: { v: string; label: string }[] = [
  { v: "all", label: "All" },
  { v: "today", label: "Today" },
  { v: "yesterday", label: "Yesterday" },
  { v: "7d", label: "Last 7 days" },
  { v: "15d", label: "Last 15 days" },
  { v: "month", label: "This Month" },
  { v: "custom", label: "Custom" },
];

const startOfDay = (t: number) => { const d = new Date(t); return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); };
// parse a "YYYY-MM-DD" date-input value into local midnight (avoids the UTC-parse off-by-one)
const localDay = (s: string) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d).getTime(); };

/** Is a lead's received_at inside the RM-table's selected range (day-granular, inclusive)? */
function inRepRange(iso: string | null, preset: string, from: string, to: string): boolean {
  if (preset === "all") return true;
  if (!iso) return false;
  const DAY = 86_400_000;
  const day = startOfDay(new Date(iso).getTime());
  const now = new Date();
  const today = startOfDay(now.getTime());
  switch (preset) {
    case "today": return day === today;
    case "yesterday": return day === today - DAY;
    case "7d": return day >= today - 6 * DAY;
    case "15d": return day >= today - 14 * DAY;
    case "month": return new Date(iso).getMonth() === now.getMonth() && new Date(iso).getFullYear() === now.getFullYear();
    case "custom": {
      const lo = from ? localDay(from) : null;
      const hi = to ? localDay(to) : null;
      return (lo == null || day >= lo) && (hi == null || day <= hi);
    }
    default: return true;
  }
}

type Rep = { rm: string; total: number; [seg: string]: number | string };
// extra per-RM signals behind the personal stat tiles (kept off Rep to avoid the index-signature clash)
type RepExtra = {
  qualified_reached: number; ever_connected: number; miss_total: number; hot: number;
  followups_overdue: number; active_days: number; leads_per_active_day: number;
};

type Row = { lead: Lead; seg: string };

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "var(--ink)", color: "var(--on-accent)", padding: "8px 11px", borderRadius: 9, fontSize: 12, boxShadow: "var(--shadow-lg)" }}>
      {label && <div style={{ fontWeight: 600, marginBottom: 3 }}>{label}</div>}
      {payload.map((p: any) => (
        <div key={p.name} style={{ display: "flex", gap: 8, justifyContent: "space-between" }}>
          <span style={{ color: "var(--line-3)" }}>{p.name}</span><b>{p.value}</b>
        </div>
      ))}
    </div>
  );
}

function pct(n: number, d: number) { return d ? Math.round((n / d) * 100) : 0; }

// treat placeholder city values ("-", "NA", blank, …) as "no city" so they don't
// show up as a real slice/row — returns the cleaned city, or null when it's junk
const CITY_PLACEHOLDERS = new Set(["", "-", "--", "—", ".", "na", "n/a", "null", "none", "nil"]);
function cleanCity(c: string | null | undefined): string | null {
  const v = (c ?? "").trim();
  return v && !CITY_PLACEHOLDERS.has(v.toLowerCase()) ? v : null;
}

type MineBundle = { rm: string; total: number; stages: Record<string, number>; extras: Record<string, number> };

// The RM's own dashboard: personal funnel tiles + stage chips. RM-only — admins
// have no equivalent on Summary; per-RM numbers are on /reports.
function MyPerformance({ mine }: { mine: MineBundle | null }) {
  if (!mine || mine.total === 0) {
    return <div className="empty" style={{ padding: 24 }}>No leads assigned to you in this range.</div>;
  }
  const ex = mine.extras;
  const tiles = [
    { label: "Total leads", value: mine.total, sub: `${ex.active_days || 0} active days · ${ex.leads_per_active_day || 0}/day` },
    { label: "Reached qualification", value: ex.qualified_reached, sub: `${pct(ex.qualified_reached, mine.total)}% of your leads` },
    { label: "Call connect rate", value: `${pct(ex.ever_connected, mine.total)}%`, sub: `${ex.ever_connected} of ${mine.total} connected` },
    { label: "Converted", value: mine.stages.converted || 0, sub: `${pct(mine.stages.converted || 0, mine.total)}% of your leads` },
    { label: "Overdue callbacks", value: ex.followups_overdue, sub: "due before today" },
    { label: "Hot leads", value: ex.hot, sub: "starred" },
  ];
  return (
    <div className="panel-pad" style={{ paddingTop: 12 }}>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
        {tiles.map((t) => (
          <div key={t.label} style={{ border: "1px solid var(--line)", borderRadius: 12, padding: "12px 14px" }}>
            <div style={{ fontSize: 11.5, color: "var(--muted)", fontWeight: 600 }}>{t.label}</div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 24, fontWeight: 700, lineHeight: 1.1, margin: "2px 0" }}>{t.value}</div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>{t.sub}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
        {STAGE_COLS.map((c) => (
          <span key={c.seg} style={{ fontSize: 12, border: "1px solid var(--line)", borderRadius: 20, padding: "4px 10px" }}>
            {c.label}: <b>{mine.stages[c.seg] || 0}</b>{" "}
            <span style={{ color: "var(--muted)" }}>({pct(mine.stages[c.seg] || 0, mine.total)}%)</span>
          </span>
        ))}
      </div>

    </div>
  );
}

export default function Analytics() {
  const { leads, isLoading } = useAllLeads(true);
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  const nav = useNavigate();
  const [trendDays, setTrendDays] = useState<number | "all">(30);
  const [repPreset, setRepPreset] = useState("month");
  const [repFrom, setRepFrom] = useState("");
  const [repTo, setRepTo] = useState("");
  // which date the range buckets on: when the lead was received vs. when it was assigned
  const [repDateBy, setRepDateBy] = useState<"received" | "assigned">("received");
  const pickRange = (v: string) => setRepPreset(v);
  const pickDateBy = (v: "received" | "assigned") => setRepDateBy(v);

  const rows: Row[] = useMemo(
    () => leads.filter((r) => !r.lead.is_test).map((r) => ({ lead: r.lead, seg: r.segment.seg })),
    [leads],
  );

  const m = useMemo(() => {
    const now = Date.now();
    const startToday = new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate()).getTime();
    const endToday = startToday + 86_400_000;
    const bySeg = (s: string) => rows.filter((r) => r.seg === s);
    const count = (s: string) => bySeg(s).length;

    // Segments are disjoint — `stage` decides the page, so each lead is returned by
    // exactly one segment. (This used to need a dedupe pass: a qualified lead with an
    // open follow-up appeared in both its stage segment and "followup".)
    const uniq = rows;

    const total = uniq.length;
    const nNew = count("new");
    const nCnr = count("call_not_received");
    const nFollowup = count("followup");
    const nQualified = count("qualified");
    const nPipeline = count("pipeline");
    const nConverted = count("converted");
    // RNR and Future Prospect have no segment of their own — both come back under
    // "rejected", so each is subtracted or a parked buyer reads as a rejected one
    const nRnr = rows.filter((r) => r.lead.stage === "rnr").length;
    const nFuture = rows.filter((r) => r.lead.stage === "future_prospect").length;
    const nRejected = count("rejected") - nRnr - nFuture;
    const qualifiedPlus = nQualified + nPipeline + nConverted; // reached qualified or beyond

    // TAT — first-contact SLA on leads still awaiting the first call (New)
    const newWithTat = bySeg("new").filter((r) => r.lead.tat_deadline);
    const tatBreached = newWithTat.filter((r) => new Date(r.lead.tat_deadline!).getTime() < now).length;
    const tatWithin = newWithTat.length - tatBreached;

    // Callbacks — kept per queue as well as combined. Call Not Received holds the
    // never-reached leads and carries a due follow_up_at exactly like Follow Up does,
    // so the combined figure is the real workload; but a tile that links to one page
    // must count only that page, or its number won't match what you land on.
    const due = (list: Row[]) => ({
      today: list.filter((r) => { const t = new Date(r.lead.follow_up_at!).getTime(); return t >= startToday && t < endToday; }).length,
      overdue: list.filter((r) => new Date(r.lead.follow_up_at!).getTime() < startToday).length,
    });
    const fuRows = rows.filter((r) => r.seg === "followup" && r.lead.follow_up_at);
    const cnrRows = rows.filter((r) => r.seg === "call_not_received" && r.lead.follow_up_at);
    const fu = [...fuRows, ...cnrRows];
    const fuDue = due(fuRows), cnrDue = due(cnrRows), allDue = due(fu);
    const fuOverdue = allDue.overdue;
    const fuToday = allDue.today;

    // Contact effectiveness (unique leads)
    const attempted = uniq.filter((r) => r.lead.ever_connected || r.lead.miss_count > 0);
    const connected = uniq.filter((r) => r.lead.ever_connected).length;
    // "need an owner" = unassigned AND still active — exclude every terminal bucket (won/rejected/RNR)
    const unassigned = uniq.filter((r) => !r.lead.assigned_to && r.seg !== "converted" && r.seg !== "rejected").length;
    const immediate = uniq.filter((r) => r.lead.plan_to_buy === HOT_PLAN).length;

    // group helper → conversion by a dimension (unique leads)
    const groupConv = (key: (l: Lead) => string | null) => {
      const map = new Map<string, { leads: number; converted: number }>();
      uniq.forEach((r) => {
        const k = key(r.lead);
        if (!k) return;
        const e = map.get(k) || { leads: 0, converted: 0 };
        e.leads += 1;
        if (r.seg === "converted") e.converted += 1;
        map.set(k, e);
      });
      return [...map.entries()].map(([k, v]) => ({ k, ...v })).sort((a, b) => b.leads - a.leads);
    };
    const bySource = groupConv((l) => l.source);
    // blank / junk cities ("-", "NA", …) collapse into one "No City" bucket so the
    // slices still sum to the overall total instead of silently dropping those leads
    const byCity = groupConv((l) => cleanCity(l.city) ?? "No City");

    return {
      total, nNew, nCnr, nFollowup, nQualified, nPipeline, nConverted, nRnr, nRejected, qualifiedPlus,
      tatBreached, tatWithin, tatTotal: newWithTat.length,
      fuOverdue, fuToday, withFu: fu.length, fuDue, cnrDue,
      attempted: attempted.length, connected, unassigned, immediate,
      bySource, byCity,
    };
  }, [rows]);

  // Per-owner counts by stage over the selected range — feeds the RM's My performance card.
  // Alongside the table rows we accumulate the extra signals the stat tiles show.
  const { repRows, repExtras } = useMemo(() => {
    const map = new Map<string, Rep>();
    const ex = new Map<string, RepExtra>();
    const days = new Map<string, Set<string>>();
    rows.forEach((r) => {
      const rm = r.lead.assigned_to;
      const when = repDateBy === "assigned" ? r.lead.assigned_at : r.lead.received_at;
      if (!rm || !inRepRange(when, repPreset, repFrom, repTo)) return;
      let e = map.get(rm);
      if (!e) { e = { rm, total: 0 }; STAGE_COLS.forEach((c) => (e![c.seg] = 0)); map.set(rm, e); }
      e.total = (e.total as number) + 1;
      if (typeof e[r.seg] === "number") e[r.seg] = (e[r.seg] as number) + 1;

      let x = ex.get(rm);
      if (!x) { x = { qualified_reached: 0, ever_connected: 0, miss_total: 0, hot: 0, followups_overdue: 0, active_days: 0, leads_per_active_day: 0 }; ex.set(rm, x); }
      if (["qualified", "pipeline", "revisit", "converted"].includes(r.seg)) x.qualified_reached += 1;
      if (r.lead.ever_connected) x.ever_connected += 1;
      x.miss_total += r.lead.miss_count || 0;
      if (r.lead.is_hot) x.hot += 1;
      if (r.lead.follow_up_at && Date.parse(r.lead.follow_up_at) < Date.now()) x.followups_overdue += 1;
      if (when) {
        let s = days.get(rm); if (!s) { s = new Set(); days.set(rm, s); }
        s.add(when.slice(0, 10));
      }
    });
    ex.forEach((x, rm) => {
      const e = map.get(rm);
      x.active_days = days.get(rm)?.size || 0;
      x.leads_per_active_day = x.active_days ? Math.round(((e!.total as number) / x.active_days) * 10) / 10 : 0;
    });
    const repRows = [...map.values()].sort((a, b) => (b.total as number) - (a.total as number));
    return { repRows, repExtras: ex };
  }, [rows, repPreset, repFrom, repTo, repDateBy]);


  const rangeLabel = (): string => {
    if (repPreset === "custom") return repFrom || repTo ? `${repFrom || "start"} → ${repTo || "today"}` : "Custom (all dates)";
    return REP_RANGES.find((r) => r.v === repPreset)?.label ?? repPreset;
  };
  // RM view: fold this RM's (already server-scoped) rows into one "me" bundle. Alias
  // variants of the same person collapse together since it's all her own data anyway.
  const mine = useMemo(() => {
    if (isAdmin || repRows.length === 0) return null;
    const stages: Record<string, number> = {};
    STAGE_COLS.forEach((c) => (stages[c.seg] = 0));
    const extras: Record<string, number> = { qualified_reached: 0, ever_connected: 0, miss_total: 0, hot: 0, followups_overdue: 0, active_days: 0, leads_per_active_day: 0 };
    let total = 0;
    repRows.forEach((r) => {
      total += r.total as number;
      STAGE_COLS.forEach((c) => (stages[c.seg] += r[c.seg] as number));
      const x = repExtras.get(r.rm);
      if (x) {
        extras.qualified_reached += x.qualified_reached;
        extras.ever_connected += x.ever_connected;
        extras.miss_total += x.miss_total;
        extras.hot += x.hot;
        extras.followups_overdue += x.followups_overdue;
        extras.active_days = Math.max(extras.active_days, x.active_days);
      }
    });
    extras.leads_per_active_day = extras.active_days ? Math.round((total / extras.active_days) * 10) / 10 : 0;
    return { rm: user?.name || repRows[0].rm, total, stages, extras };
  }, [isAdmin, repRows, repExtras, user]);

  // Inflow by received_at over the selected window (own memo so switching the range
  // doesn't recompute everything). "All" spans from the earliest lead to today.
  const inflow = useMemo(() => {
    const map = new Map<string, number>();
    let earliest = Infinity;
    rows.forEach((r) => {
      if (!r.lead.received_at) return;
      const d = new Date(r.lead.received_at);
      map.set(d.toISOString().slice(0, 10), (map.get(d.toISOString().slice(0, 10)) || 0) + 1);
      earliest = Math.min(earliest, d.getTime());
    });
    const base = new Date();
    const startOf = (t: number) => { const x = new Date(t); return new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime(); };
    const todayStart = startOf(base.getTime());
    const days = trendDays === "all"
      ? (earliest === Infinity ? 30 : Math.min(366, Math.round((todayStart - startOf(earliest)) / 86_400_000) + 1))
      : trendDays;
    const out: { label: string; c: number }[] = [];
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(base); d.setDate(base.getDate() - i);
      out.push({ label: d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }), c: map.get(d.toISOString().slice(0, 10)) || 0 });
    }
    return out;
  }, [rows, trendDays]);

  if (isLoading && rows.length === 0) {
    return <div className="card"><div className="empty" style={{ padding: 48 }}>Loading analytics…</div></div>;
  }

  const srcData = m.bySource.map((s) => ({ ...s, label: srcLabel(s.k) }));
  const cityData = m.byCity.map((s, i) => ({ ...s, label: s.k, color: CITY_COLORS[i % CITY_COLORS.length] }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <LeadFunnel />
      {/* My performance — an RM's own stage breakdown over a date range. The admin
          "RM performance" table that shared this card was removed 14 Sep; per-RM
          numbers for managers live on /reports. */}
      {!isAdmin && (
      <div style={card}>
        <div className="panel-pad" style={{ paddingBottom: 0 }}>
          <div className="panel-title" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <span><IconChart /> My performance</span>
            <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
              {REP_RANGES.map((r) => (
                <button key={r.v} className={"btn sm " + (repPreset === r.v ? "" : "ghost")}
                  style={repPreset === r.v ? { background: "var(--brand)", color: "var(--on-brand)" } : undefined}
                  onClick={() => pickRange(r.v)}>{r.label}</button>
              ))}
              {repPreset === "custom" && (
                <>
                  <input type="date" value={repFrom} onChange={(e) => setRepFrom(e.target.value)} style={{ padding: "5px 8px", fontSize: 12 }} title="From" />
                  <span style={{ color: "var(--muted)" }}>–</span>
                  <input type="date" value={repTo} onChange={(e) => setRepTo(e.target.value)} style={{ padding: "5px 8px", fontSize: 12 }} title="To" />
                </>
              )}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, margin: "6px 0 0" }}>
            <p className="note" style={{ margin: 0, fontSize: 11.5 }}>
              Your funnel over the selected range.
            </p>
            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "var(--muted)" }}>Bucket by</span>
              {([["received", "Received date"], ["assigned", "Assigned date"]] as const).map(([v, label]) => (
                <button key={v} className={"btn sm " + (repDateBy === v ? "" : "ghost")}
                  style={repDateBy === v ? { background: "var(--brand)", color: "var(--on-brand)" } : undefined}
                  title={v === "received" ? "Range filters on when the lead was received" : "Range filters on when the lead was assigned to its current owner"}
                  onClick={() => pickDateBy(v)}>{label}</button>
              ))}
            </div>
          </div>
        </div>
        <MyPerformance mine={mine} />
      </div>
      )}

      {/* inflow trend */}
      <div style={card} className="panel-pad">
        <div className="panel-title" style={{ justifyContent: "space-between" }}>
          <span><IconTrend /> Leads received · {trendDays === "all" ? "all time" : `last ${trendDays} days`}</span>
          <div style={{ display: "flex", gap: 4 }}>
            {TREND_RANGES.map((r) => (
              <button key={String(r.v)} className={"btn sm " + (trendDays === r.v ? "" : "ghost")}
                style={trendDays === r.v ? { background: "var(--brand)", color: "var(--on-brand)" } : undefined}
                onClick={() => setTrendDays(r.v)}>{r.label}</button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={inflow} margin={{ left: -18, right: 8, top: 8 }}>
            <defs>
              <linearGradient id="ia" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--blue)" stopOpacity={0.32} />
                <stop offset="100%" stopColor="var(--blue)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted)" }} interval={Math.max(0, Math.floor(inflow.length / 8))} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip content={<ChartTooltip />} />
            <Area type="monotone" dataKey="c" name="Leads" stroke="var(--blue)" strokeWidth={2.5} fill="url(#ia)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* source + city conversion */}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={card} className="panel-pad">
          <div className="panel-title"><IconMegaphone /> By source</div>
          {srcData.length === 0 ? (
            <div className="empty" style={{ padding: 20 }}>No data.</div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={srcData} dataKey="leads" nameKey="label" innerRadius={50} outerRadius={78} paddingAngle={2} stroke="none">
                    {srcData.map((s) => <Cell key={s.k} fill={sourceColor(s.k)} />)}
                  </Pie>
                  <Tooltip content={<ChartTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
                {srcData.map((s) => (
                  <div key={s.k} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 3, background: sourceColor(s.k), flex: "none" }} />
                    <span style={{ fontWeight: 600 }}>{s.label}</span>
                    <span style={{ marginLeft: "auto", color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
                      <b style={{ color: "var(--ink)" }}>{s.leads}</b> · {pct(s.converted, s.leads)}% conversion
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
        <div style={card} className="panel-pad">
          <div className="panel-title"><IconCity /> By city</div>
          {cityData.length === 0 ? (
            <div className="empty" style={{ padding: 20 }}>No data.</div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={cityData} dataKey="leads" nameKey="label" innerRadius={50} outerRadius={78} paddingAngle={2} stroke="none">
                    {cityData.map((s) => <Cell key={s.k} fill={s.color} />)}
                  </Pie>
                  <Tooltip content={<ChartTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
                {cityData.map((s) => (
                  <div key={s.k} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 3, background: s.color, flex: "none" }} />
                    <span style={{ fontWeight: 600 }}>{s.label}</span>
                    <span style={{ marginLeft: "auto", color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
                      <b style={{ color: "var(--ink)" }}>{s.leads}</b> · {pct(s.converted, s.leads)}% conversion
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
