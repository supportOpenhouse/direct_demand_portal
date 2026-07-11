/* Analytics — measurable lead & supply parameters, computed client-side from the
   full lead set (all segments) + the supply pipeline. Opened from the Dashboard's
   Analytics toggle; the existing overview is left untouched. No backend changes:
   everything here is derived from data the app already loads.

   Definitions are labelled inline so every number is unambiguous. `new Date()` is
   fine here (browser runtime). Test leads (is_test) are excluded throughout. */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell } from "recharts";
import { useAllLeads, useSupply } from "../lib/queries";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { srcLabel } from "../lib/leads";
import { Lead } from "../lib/api";

const SOURCE_COLOR: Record<string, string> = { meta: "#2563eb", "99acres": "#e85d2a", magicbricks: "#e63a73" };
const sourceColor = (s: string) => SOURCE_COLOR[s] || "var(--slate)";
const card = { background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "var(--radius)", boxShadow: "var(--shadow)" } as const;
const HOT_PLAN = "Within 30 days";

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

/** labelled progress meter — `value` of `total`, shown as a count + percent */
function Meter({ label, value, total, color, suffix = "" }: { label: string; value: number; total: number; color: string; suffix?: string }) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div style={{ marginBottom: 13 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 5 }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span style={{ fontFamily: "'Spline Sans Mono'", color: "var(--muted)" }}>
          <b style={{ color: "var(--ink)" }}>{value}</b>{suffix} · {pct}%
        </span>
      </div>
      <div style={{ height: 9, background: "var(--line)", borderRadius: 6, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 6, transition: ".5s" }} />
      </div>
    </div>
  );
}

/** one row of a "conversion" table — a magnitude bar for volume + a converted/total · % readout */
function ConvRow({ label, chip, leads, converted, max, color }: { label: string; chip?: React.ReactNode; leads: number; converted: number; max: number; color: string }) {
  const conv = leads ? Math.round((converted / leads) * 100) : 0;
  return (
    <div style={{ marginBottom: 11 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 4, gap: 8 }}>
        <span style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>{chip}{label}</span>
        <span style={{ color: "var(--muted)", whiteSpace: "nowrap", fontFamily: "'Spline Sans Mono'" }}>
          <b style={{ color: "var(--ink)" }}>{converted}</b>/{leads} · {conv}%
        </span>
      </div>
      <div style={{ height: 8, background: "var(--line)", borderRadius: 6, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${max ? (leads / max) * 100 : 0}%`, background: color, borderRadius: 6 }} />
      </div>
    </div>
  );
}

function pct(n: number, d: number) { return d ? Math.round((n / d) * 100) : 0; }

export default function Analytics() {
  const { leads, isLoading } = useAllLeads(true);
  const { data: supply } = useSupply();
  const nav = useNavigate();
  const [city, setCity] = useState("");

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

    const total = rows.length;
    const nNew = count("new");
    const nFollowup = count("followup");
    const nQualified = count("qualified");
    const nPipeline = count("pipeline");
    const nConverted = count("converted");
    const nRnr = count("rnr");
    const nRejected = count("rejected");
    const qualifiedPlus = nQualified + nPipeline + nConverted; // reached qualified or beyond

    // TAT — first-contact SLA on leads still awaiting the first call (New)
    const newWithTat = bySeg("new").filter((r) => r.lead.tat_deadline);
    const tatBreached = newWithTat.filter((r) => new Date(r.lead.tat_deadline!).getTime() < now).length;
    const tatWithin = newWithTat.length - tatBreached;

    // Follow-ups
    const withFu = rows.filter((r) => r.lead.follow_up_at);
    const fuOverdue = withFu.filter((r) => new Date(r.lead.follow_up_at!).getTime() < startToday).length;
    const fuToday = withFu.filter((r) => { const t = new Date(r.lead.follow_up_at!).getTime(); return t >= startToday && t < endToday; }).length;

    // Contact effectiveness
    const attempted = rows.filter((r) => r.lead.ever_connected || r.lead.miss_count > 0);
    const connected = rows.filter((r) => r.lead.ever_connected).length;
    const unassigned = rows.filter((r) => !r.lead.assigned_to && r.seg !== "converted" && r.seg !== "rejected").length;
    const immediate = rows.filter((r) => r.lead.plan_to_buy === HOT_PLAN).length;

    // group helper → conversion by a dimension
    const groupConv = (key: (l: Lead) => string | null) => {
      const map = new Map<string, { leads: number; converted: number }>();
      rows.forEach((r) => {
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

    // Per-RM leaderboard
    const rmMap = new Map<string, { assigned: number; connected: number; qualified: number; converted: number }>();
    rows.forEach((r) => {
      const rm = r.lead.assigned_to;
      if (!rm) return;
      const e = rmMap.get(rm) || { assigned: 0, connected: 0, qualified: 0, converted: 0 };
      e.assigned += 1;
      if (r.lead.ever_connected) e.connected += 1;
      if (r.seg === "qualified" || r.seg === "pipeline" || r.seg === "converted") e.qualified += 1;
      if (r.seg === "converted") e.converted += 1;
      rmMap.set(rm, e);
    });
    const reps = [...rmMap.entries()].map(([rm, v]) => ({ rm, ...v })).sort((a, b) => b.converted - a.converted || b.assigned - a.assigned);

    // Inflow — last 30 days by received_at
    const inflowMap = new Map<string, number>();
    rows.forEach((r) => { if (r.lead.received_at) { const k = new Date(r.lead.received_at).toISOString().slice(0, 10); inflowMap.set(k, (inflowMap.get(k) || 0) + 1); } });
    const inflow: { label: string; c: number }[] = [];
    const base = new Date();
    for (let i = 29; i >= 0; i--) {
      const d = new Date(base); d.setDate(base.getDate() - i);
      inflow.push({ label: d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }), c: inflowMap.get(d.toISOString().slice(0, 10)) || 0 });
    }

    return {
      total, nNew, nFollowup, nQualified, nPipeline, nConverted, nRnr, nRejected, qualifiedPlus,
      tatBreached, tatWithin, tatTotal: newWithTat.length,
      fuOverdue, fuToday, withFu: withFu.length,
      attempted: attempted.length, connected, unassigned, immediate,
      bySource, byCity, reps, inflow,
    };
  }, [rows]);

  // supply pipeline snapshot (units by stage)
  const supplyStages = useMemo(() => {
    const items = supply?.items ?? [];
    const map = new Map<string, number>();
    items.forEach((s) => map.set(s.stage, (map.get(s.stage) || 0) + 1));
    return { total: items.length, stages: [...map.entries()].map(([stage, c]) => ({ stage, c })).sort((a, b) => b.c - a.c) };
  }, [supply]);

  if (isLoading && rows.length === 0) {
    return <div className="card"><div className="empty" style={{ padding: 48 }}>Loading analytics…</div></div>;
  }

  const convRate = pct(m.nConverted, m.total);
  const srcData = m.bySource.map((s) => ({ ...s, label: srcLabel(s.k) }));
  const cityMax = Math.max(...m.byCity.map((s) => s.leads), 1);
  const repMax = Math.max(...m.reps.map((r) => r.assigned), 1);
  const supMax = Math.max(...supplyStages.stages.map((s) => s.c), 1);

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

      {/* KPI row */}
      <div className="grid" style={{ gridTemplateColumns: "repeat(6, 1fr)", gap: 14 }}>
        <Tile label="New Leads" value={m.nNew.toLocaleString("en-IN")} sub="awaiting first call" accent="var(--blue)" onClick={() => nav("/leads/new")} />
        <Tile label="Follow-ups Today" value={m.fuToday} sub={`${m.fuOverdue} overdue`} accent="var(--amber)" onClick={() => nav("/leads/followup")} />
        <Tile label="TAT Breached" value={m.tatBreached} sub={`of ${m.tatTotal} new · SLA`} accent="var(--coral)" onClick={() => nav("/leads/new")} />
        <Tile label="Qualified+" value={m.qualifiedPlus.toLocaleString("en-IN")} sub={`${pct(m.qualifiedPlus, m.total)}% of leads`} accent="var(--cyan)" onClick={() => nav("/leads/qualified")} />
        <Tile label="Converted" value={m.nConverted.toLocaleString("en-IN")} sub={`${convRate}% lead→token`} accent="var(--emerald)" onClick={() => nav("/leads/converted")} />
        <Tile label="Unassigned" value={m.unassigned} sub="need an owner" accent="var(--gold)" onClick={() => nav("/leads/new")} />
      </div>

      {/* funnel + SLA/contact */}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={card} className="panel-pad">
          <div className="panel-title">🪜 Funnel & conversion</div>
          <Meter label="New" value={m.nNew} total={Math.max(m.total, 1)} color="var(--blue)" />
          <Meter label="Qualified (incl. pipeline)" value={m.qualifiedPlus} total={Math.max(m.total, 1)} color="var(--cyan)" />
          <Meter label="Converted (token)" value={m.nConverted} total={Math.max(m.total, 1)} color="var(--emerald)" />
          <div className="note" style={{ marginTop: 6 }}>
            {pct(m.nConverted, m.qualifiedPlus)}% of qualified leads convert · {m.nRejected + m.nRnr} lost (rejected + RNR).
          </div>
        </div>

        <div style={card} className="panel-pad">
          <div className="panel-title">⏱ SLA & contact</div>
          <Meter label="New leads within TAT window" value={m.tatWithin} total={Math.max(m.tatTotal, 1)} color="var(--emerald)" />
          <Meter label="Follow-ups due today" value={m.fuToday} total={Math.max(m.withFu, 1)} color="var(--amber)" />
          <Meter label="Call connect rate" value={m.connected} total={Math.max(m.attempted, 1)} color="var(--cyan)" />
          <Meter label="RNR (never reached)" value={m.nRnr} total={Math.max(m.total, 1)} color="var(--coral)" />
          <div className="note" style={{ marginTop: 6 }}>Connect rate = ever-connected / leads with a call attempt.</div>
        </div>
      </div>

      {/* inflow trend */}
      <div style={card} className="panel-pad">
        <div className="panel-title">📈 Leads received · last 30 days</div>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={m.inflow} margin={{ left: -18, right: 8, top: 8 }}>
            <defs>
              <linearGradient id="ia" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2563eb" stopOpacity={0.32} />
                <stop offset="100%" stopColor="#2563eb" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted)" }} interval={4} tickLine={false} axisLine={false} />
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
                      <b style={{ color: "var(--ink)" }}>{s.leads}</b> · {pct(s.converted, s.leads)}% conv
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
        <div style={card} className="panel-pad">
          <div className="panel-title">🏙 Conversion by city</div>
          {m.byCity.slice(0, 8).map((s) => (
            <ConvRow key={s.k} label={s.k} leads={s.leads} converted={s.converted} max={cityMax} color="var(--indigo)" />
          ))}
          {m.byCity.length === 0 && <div className="empty" style={{ padding: 20 }}>No data.</div>}
        </div>
      </div>

      {/* per-RM leaderboard */}
      <div style={card}>
        <div className="panel-pad" style={{ paddingBottom: 0 }}><div className="panel-title">👥 Rep performance</div></div>
        {m.reps.length === 0 ? (
          <div className="empty" style={{ padding: 24 }}>No assigned leads yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Owner</th>
                <th style={{ textAlign: "right" }}>Assigned</th>
                <th style={{ textAlign: "right" }}>Connect %</th>
                <th style={{ textAlign: "right" }}>Qualified</th>
                <th style={{ textAlign: "right" }}>Converted</th>
                <th style={{ minWidth: 120 }}>Conversion</th>
              </tr>
            </thead>
            <tbody>
              {m.reps.map((r) => {
                const cv = pct(r.converted, r.assigned);
                return (
                  <tr key={r.rm}>
                    <td style={{ fontWeight: 600 }}>{r.rm}</td>
                    <td style={{ textAlign: "right", fontFamily: "'Spline Sans Mono'" }}>{r.assigned}</td>
                    <td style={{ textAlign: "right", fontFamily: "'Spline Sans Mono'", color: "var(--ink-2)" }}>{pct(r.connected, r.assigned)}%</td>
                    <td style={{ textAlign: "right", fontFamily: "'Spline Sans Mono'", color: "var(--ink-2)" }}>{r.qualified}</td>
                    <td style={{ textAlign: "right", fontFamily: "'Spline Sans Mono'", fontWeight: 700, color: "var(--emerald)" }}>{r.converted}</td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ flex: 1, height: 7, background: "var(--line)", borderRadius: 6, overflow: "hidden" }}>
                          <div style={{ height: "100%", width: `${(r.assigned / repMax) * 100}%`, background: "var(--blue)", borderRadius: 6 }} />
                        </div>
                        <span style={{ fontFamily: "'Spline Sans Mono'", fontSize: 11.5, color: "var(--muted)", width: 34, textAlign: "right" }}>{cv}%</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* supply snapshot */}
      {supplyStages.total > 0 && (
        <div style={card} className="panel-pad">
          <div className="panel-title">🏗 Supply pipeline · {supplyStages.total.toLocaleString("en-IN")} units</div>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: "2px 24px" }}>
            {supplyStages.stages.map((s) => (
              <div key={s.stage} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 4 }}>
                  <span style={{ fontWeight: 600 }}>{s.stage}</span>
                  <span style={{ fontFamily: "'Spline Sans Mono'", color: "var(--muted)" }}>{s.c}</span>
                </div>
                <div style={{ height: 7, background: "var(--line)", borderRadius: 6, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${(s.c / supMax) * 100}%`, background: "var(--cyan)", borderRadius: 6 }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
