/* Analytics — measurable lead & supply parameters, computed client-side from the
   full lead set (all segments) + the supply pipeline. Opened from the Dashboard's
   Analytics toggle; the existing overview is left untouched. No backend changes:
   everything here is derived from data the app already loads.

   Definitions are labelled inline so every number is unambiguous. `new Date()` is
   fine here (browser runtime). Test leads (is_test) are excluded throughout. */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell } from "recharts";
import { useAllLeads } from "../lib/queries";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { useSort, SortTh } from "../lib/useSort";
import { srcLabel } from "../lib/leads";
import { Lead } from "../lib/api";

const SOURCE_COLOR: Record<string, string> = { meta: "#2563eb", "99acres": "#e85d2a", magicbricks: "#e63a73" };
const sourceColor = (s: string) => SOURCE_COLOR[s] || "var(--slate)";
// categorical palette for the city donut (assigned in byCity order, fixed)
const CITY_COLORS = ["#4f46e5", "#0e8fa8", "#d68309", "#e11d48", "#059669", "#7c3aed", "#0891b2", "#64748b"];
const TREND_RANGES: { v: number | "all"; label: string }[] = [
  { v: 7, label: "7d" }, { v: 15, label: "15d" }, { v: 30, label: "30d" }, { v: "all", label: "All" },
];
const card = { background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "var(--radius)", boxShadow: "var(--shadow)" } as const;
const HOT_PLAN = "Within 30 days";

// RM performance: one column per lead stage/segment, in funnel order (matches the tabs)
const STAGE_COLS: { seg: string; label: string }[] = [
  { seg: "new", label: "New" },
  { seg: "call_not_received", label: "Call Not Received" },
  { seg: "followup", label: "Call Back Again" },
  { seg: "qualified", label: "Qualified" },
  { seg: "pipeline", label: "Visited" },
  { seg: "revisit", label: "Pipeline" },
  { seg: "converted", label: "Converted" },
  { seg: "rejected", label: "Rejected" },
];
const REP_RANGES: { v: string; label: string }[] = [
  { v: "today", label: "Today" },
  { v: "yesterday", label: "Yesterday" },
  { v: "7d", label: "Last 7 days" },
  { v: "15d", label: "Last 15 days" },
  { v: "month", label: "This Month" },
  { v: "custom", label: "Custom" },
];

const startOfDay = (t: number) => { const d = new Date(t); return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); };

/** Is a lead's received_at inside the RM-table's selected range (day-granular, inclusive)? */
function inRepRange(iso: string | null, preset: string, from: string, to: string): boolean {
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
      const lo = from ? startOfDay(new Date(from).getTime()) : null;
      const hi = to ? startOfDay(new Date(to).getTime()) : null;
      return (lo == null || day >= lo) && (hi == null || day <= hi);
    }
    default: return true;
  }
}

type Rep = { rm: string; total: number; [seg: string]: number | string };

type Row = { lead: Lead; seg: string };

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "var(--ink)", color: "#fff", padding: "8px 11px", borderRadius: 9, fontSize: 12, boxShadow: "var(--shadow-lg)" }}>
      {label && <div style={{ fontWeight: 600, marginBottom: 3 }}>{label}</div>}
      {payload.map((p: any) => (
        <div key={p.name} style={{ display: "flex", gap: 8, justifyContent: "space-between" }}>
          <span style={{ color: "#cbd5e1" }}>{p.name}</span><b>{p.value}</b>
        </div>
      ))}
    </div>
  );
}

function Tile({ label, value, sub, accent, onClick }: { label: string; value: React.ReactNode; sub: string; accent: string; onClick?: () => void }) {
  return (
    <div className={"card stat" + (onClick ? " clickable" : "")} style={{ ["--accent" as any]: accent }} onClick={onClick}>
      <div className="k">{label}</div>
      <div className="v" style={{ color: accent }}>{value}</div>
      <div className="d" style={{ color: "var(--muted)", fontWeight: 500 }}>{sub}</div>
    </div>
  );
}


function pct(n: number, d: number) { return d ? Math.round((n / d) * 100) : 0; }

export default function Analytics() {
  const { leads, isLoading } = useAllLeads(true);
  const nav = useNavigate();
  const [city, setCity] = useState("");
  const [trendDays, setTrendDays] = useState<number | "all">(30);
  const [repPreset, setRepPreset] = useState("month");
  const [repFrom, setRepFrom] = useState("");
  const [repTo, setRepTo] = useState("");

  const rows: Row[] = useMemo(
    () => leads.filter((r) => !r.lead.is_test && (!city || r.lead.city === city)).map((r) => ({ lead: r.lead, seg: r.segment.seg })),
    [leads, city],
  );
  const cityOptions = useMemo(() => uniqueValues(leads.map((r) => r.lead), (l) => l.city), [leads]);

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
    // RNR has no segment of its own — those leads come back under "rejected"
    const nRnr = rows.filter((r) => r.lead.stage === "rnr").length;
    const nRejected = count("rejected") - nRnr;
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
    const byCity = groupConv((l) => l.city);

    return {
      total, nNew, nCnr, nFollowup, nQualified, nPipeline, nConverted, nRnr, nRejected, qualifiedPlus,
      tatBreached, tatWithin, tatTotal: newWithTat.length,
      fuOverdue, fuToday, withFu: fu.length, fuDue, cnrDue,
      attempted: attempted.length, connected, unassigned, immediate,
      bySource, byCity,
    };
  }, [rows]);

  // RM performance: per-owner counts by stage, over the selected date range (received_at)
  const repRows = useMemo<Rep[]>(() => {
    const map = new Map<string, Rep>();
    rows.forEach((r) => {
      const rm = r.lead.assigned_to;
      if (!rm || !inRepRange(r.lead.received_at, repPreset, repFrom, repTo)) return;
      let e = map.get(rm);
      if (!e) { e = { rm, total: 0 }; STAGE_COLS.forEach((c) => (e![c.seg] = 0)); map.set(rm, e); }
      e.total = (e.total as number) + 1;
      if (typeof e[r.seg] === "number") e[r.seg] = (e[r.seg] as number) + 1;
    });
    return [...map.values()].sort((a, b) => (b.total as number) - (a.total as number));
  }, [rows, repPreset, repFrom, repTo]);

  const { sorted: repList, sortKey, dir, onSort } = useSort<Rep>(repRows, {
    name: (r) => r.rm,
    total: (r) => r.total as number,
    new: (r) => r.new as number,
    call_not_received: (r) => r.call_not_received as number,
    followup: (r) => r.followup as number,
    qualified: (r) => r.qualified as number,
    pipeline: (r) => r.pipeline as number,
    revisit: (r) => r.revisit as number,
    converted: (r) => r.converted as number,
    rejected: (r) => r.rejected as number,
  });

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

  const convRate = pct(m.nConverted, m.total);
  const srcData = m.bySource.map((s) => ({ ...s, label: srcLabel(s.k) }));
  const cityData = m.byCity.map((s, i) => ({ ...s, label: s.k, color: CITY_COLORS[i % CITY_COLORS.length] }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* filter bar */}
      <div className="section-head" style={{ marginBottom: 0 }}>
        <div className="note">
          Computed live across all lead stages{city ? ` · ${city}` : ""} · {m.total.toLocaleString("en-IN")} leads
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <FilterSelect label="City" value={city} options={cityOptions} onChange={setCity} width={150} />
          {city && <button className="btn ghost sm" onClick={() => setCity("")}>Clear</button>}
        </div>
      </div>

      {/* RM performance — per-owner stage breakdown over a date range */}
      <div style={card}>
        <div className="panel-pad" style={{ paddingBottom: 0 }}>
          <div className="panel-title" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <span>👥 RM performance</span>
            <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
              {REP_RANGES.map((r) => (
                <button key={r.v} className={"btn sm " + (repPreset === r.v ? "" : "ghost")}
                  style={repPreset === r.v ? { background: "var(--blue)", color: "#fff" } : undefined}
                  onClick={() => setRepPreset(r.v)}>{r.label}</button>
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
          <p className="note" style={{ margin: "0 0 4px" }}>Each cell is the RM's leads in that stage · % of their total for the range.</p>
        </div>
        {repList.length === 0 ? (
          <div className="empty" style={{ padding: 24 }}>No assigned leads in this range.</div>
        ) : (
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <SortTh label="Assigned To" sortKey="name" activeKey={sortKey} dir={dir} onSort={onSort} />
                <SortTh label="Total" sortKey="total" activeKey={sortKey} dir={dir} onSort={onSort} align="right" style={{ width: 92, whiteSpace: "normal", verticalAlign: "bottom" }} />
                {STAGE_COLS.map((c) => (
                  <SortTh key={c.seg} label={c.label} sortKey={c.seg} activeKey={sortKey} dir={dir} onSort={onSort} align="right" style={{ width: 92, whiteSpace: "normal", verticalAlign: "bottom" }} />
                ))}
              </tr>
            </thead>
            <tbody>
              {repList.map((r) => (
                <tr key={r.rm}>
                  <td style={{ fontWeight: 600, whiteSpace: "nowrap" }}>{r.rm}</td>
                  <td style={{ textAlign: "right", fontFamily: "'Spline Sans Mono'", fontWeight: 700, whiteSpace: "nowrap" }}>{r.total as number}</td>
                  {STAGE_COLS.map((c) => {
                    const n = r[c.seg] as number;
                    return (
                      <td key={c.seg} style={{ textAlign: "right", fontFamily: "'Spline Sans Mono'", whiteSpace: "nowrap" }}>
                        {n}{" "}<span style={{ color: "var(--muted)" }}>({pct(n, r.total as number)}%)</span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>

      {/* inflow trend */}
      <div style={card} className="panel-pad">
        <div className="panel-title" style={{ justifyContent: "space-between" }}>
          <span>📈 Leads received · {trendDays === "all" ? "all time" : `last ${trendDays} days`}</span>
          <div style={{ display: "flex", gap: 4 }}>
            {TREND_RANGES.map((r) => (
              <button key={String(r.v)} className={"btn sm " + (trendDays === r.v ? "" : "ghost")}
                style={trendDays === r.v ? { background: "var(--blue)", color: "#fff" } : undefined}
                onClick={() => setTrendDays(r.v)}>{r.label}</button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={inflow} margin={{ left: -18, right: 8, top: 8 }}>
            <defs>
              <linearGradient id="ia" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2563eb" stopOpacity={0.32} />
                <stop offset="100%" stopColor="#2563eb" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted)" }} interval={Math.max(0, Math.floor(inflow.length / 8))} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip content={<ChartTooltip />} />
            <Area type="monotone" dataKey="c" name="Leads" stroke="#2563eb" strokeWidth={2.5} fill="url(#ia)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* source + city conversion */}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={card} className="panel-pad">
          <div className="panel-title">📣 By source</div>
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
                    <span style={{ marginLeft: "auto", color: "var(--muted)", fontFamily: "'Spline Sans Mono'" }}>
                      <b style={{ color: "var(--ink)" }}>{s.leads}</b> · {pct(s.converted, s.leads)}% conversion
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
        <div style={card} className="panel-pad">
          <div className="panel-title">🏙 By city</div>
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
                    <span style={{ marginLeft: "auto", color: "var(--muted)", fontFamily: "'Spline Sans Mono'" }}>
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
