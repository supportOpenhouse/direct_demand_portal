/* Dashboard — interactive overview of the lead funnel. Role-scoped via the API. */
import { useNavigate } from "react-router-dom";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, BarChart, Bar,
} from "recharts";
import { useDashboard, formatDate } from "../lib/queries";
import { useAuth } from "../components/AuthContext";
import { srcClass, srcLabel, stageClass, stageLabel, initials } from "../lib/leads";

const SOURCE_COLOR: Record<string, string> = { meta: "#1877f2", "99acres": "#ed5a0a", magicbricks: "#e63a73" };
const sourceColor = (s: string) => SOURCE_COLOR[s] || "#64748b";

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

// fill the last 30 calendar days so the trend axis is continuous
function fill30(by_day: { day: string; c: number }[]) {
  const map = new Map(by_day.map((d) => [d.day, d.c]));
  const out: { day: string; label: string; c: number }[] = [];
  const now = new Date();
  for (let i = 29; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(now.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    out.push({ day: key, label: d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }), c: map.get(key) || 0 });
  }
  return out;
}

function Kpi({ label, value, sub, accent, icon, onClick }: { label: string; value: number; sub: string; accent: string; icon: string; onClick?: () => void }) {
  return (
    <div className={"card stat" + (onClick ? " clickable" : "")} style={{ ["--accent" as any]: accent }} onClick={onClick}>
      <div className="ico" style={{ background: accent + "22", color: accent }}>{icon}</div>
      <div className="k">{label}</div>
      <div className="v" style={{ color: accent }}>{value.toLocaleString("en-IN")}</div>
      <div className="d" style={{ color: "var(--muted)", fontWeight: 500 }}>{sub}</div>
    </div>
  );
}

function FunnelBar({ label, value, max, color, onClick }: { label: string; value: number; max: number; color: string; onClick?: () => void }) {
  return (
    <div style={{ marginBottom: 13, cursor: onClick ? "pointer" : "default" }} onClick={onClick}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 5 }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span style={{ fontFamily: "'Spline Sans Mono'", color: "var(--muted)" }}>{value}</span>
      </div>
      <div style={{ height: 12, background: "var(--line)", borderRadius: 7, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${max ? (value / max) * 100 : 0}%`, background: color, borderRadius: 7, transition: ".6s" }} />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { data, isLoading } = useDashboard();
  const { user } = useAuth();
  const nav = useNavigate();
  const name = (user?.name || "there").split(" ")[0];

  if (isLoading || !data || data.status !== "ok") {
    return <div className="card"><div className="empty" style={{ padding: 48 }}>{isLoading ? "Loading dashboard…" : "Dashboard unavailable."}</div></div>;
  }
  const t = data.totals;
  const trend = fill30(data.by_day);
  const funnelMax = Math.max(t.new, t.qualified, t.pipeline, t.converted, 1);
  const card = { background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "var(--radius)", boxShadow: "var(--shadow)" } as const;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="section-head" style={{ marginBottom: 0 }}>
        <div>
          <h1 style={{ fontFamily: "'Bricolage Grotesque'", fontSize: 24, margin: 0, letterSpacing: "-.02em" }}>Hello, {name} 👋</h1>
          <p className="sec-sub" style={{ margin: "2px 0 0" }}>
            {t.total.toLocaleString("en-IN")} leads in your view · {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}
          </p>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid" style={{ gridTemplateColumns: "repeat(6, 1fr)", gap: 14 }}>
        <Kpi label="New Leads" value={t.new} sub="awaiting first call" accent="#2563eb" icon="✦" onClick={() => nav("/leads/new")} />
        <Kpi label="Qualified" value={t.qualified} sub="confirmed · < 7 days" accent="#0e8fa8" icon="✓" onClick={() => nav("/leads/qualified")} />
        <Kpi label="Immediate Buyers" value={t.immediate} sub="plan to buy < 30d" accent="#e85d2a" icon="🔥" />
        <Kpi label="Pipeline" value={t.pipeline} sub="aged 7+ days" accent="#4f46e5" icon="▶" onClick={() => nav("/leads/pipeline")} />
        <Kpi label="Converted" value={t.converted} sub={`${data.conversion_rate}% conversion`} accent="#059669" icon="🏆" onClick={() => nav("/leads/converted")} />
        <Kpi label="Unassigned" value={t.unassigned} sub="need an owner" accent="#e11d48" icon="◎" onClick={() => nav("/leads/new")} />
      </div>

      {/* trend + source */}
      <div className="grid" style={{ gridTemplateColumns: "2fr 1fr", gap: 16 }}>
        <div style={card} className="panel-pad">
          <div className="panel-title">📈 Leads received · last 30 days</div>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={trend} margin={{ left: -18, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2563eb" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#2563eb" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted)" }} interval={4} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="c" name="Leads" stroke="#2563eb" strokeWidth={2.5} fill="url(#g)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div style={card} className="panel-pad">
          <div className="panel-title">By source</div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={data.by_source} dataKey="c" nameKey="source" innerRadius={52} outerRadius={82} paddingAngle={2} stroke="none">
                {data.by_source.map((s) => <Cell key={s.source} fill={sourceColor(s.source)} />)}
              </Pie>
              <Tooltip content={<ChartTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
            {data.by_source.map((s) => (
              <div key={s.source} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
                <span style={{ width: 9, height: 9, borderRadius: 3, background: sourceColor(s.source) }} />
                <span className={`src ${srcClass(s.source)}`}>{srcLabel(s.source)}</span>
                <b style={{ marginLeft: "auto", fontFamily: "'Spline Sans Mono'" }}>{s.c}</b>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* funnel + city + RM */}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
        <div style={card} className="panel-pad">
          <div className="panel-title">🪜 Lifecycle funnel</div>
          <FunnelBar label="New" value={t.new} max={funnelMax} color="#2563eb" onClick={() => nav("/leads/new")} />
          <FunnelBar label="Qualified" value={t.qualified} max={funnelMax} color="#0e8fa8" onClick={() => nav("/leads/qualified")} />
          <FunnelBar label="Pipeline" value={t.pipeline} max={funnelMax} color="#4f46e5" onClick={() => nav("/leads/pipeline")} />
          <FunnelBar label="Converted" value={t.converted} max={funnelMax} color="#059669" onClick={() => nav("/leads/converted")} />
          <div className="note" style={{ marginTop: 6 }}>{data.conversion_rate}% of confirmed leads convert to a token.</div>
        </div>

        <div style={card} className="panel-pad">
          <div className="panel-title">🏙 By city</div>
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={data.by_city} layout="vertical" margin={{ left: 10, right: 12 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="city" width={88} tick={{ fontSize: 11, fill: "var(--ink-2)" }} tickLine={false} axisLine={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--panel-2)" }} />
              <Bar dataKey="c" name="Leads" fill="#7c3aed" radius={[0, 5, 5, 0]} barSize={16} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div style={card} className="panel-pad">
          <div className="panel-title">👥 Leads by owner</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {data.by_assignee.map((a) => {
              const max = Math.max(...data.by_assignee.map((x) => x.c), 1);
              const isUn = a.name === "Unassigned";
              return (
                <div key={a.name}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600, color: isUn ? "var(--coral)" : "var(--ink)" }}>{a.name}</span>
                    <span style={{ fontFamily: "'Spline Sans Mono'", color: "var(--muted)" }}>{a.c}</span>
                  </div>
                  <div style={{ height: 8, background: "var(--line)", borderRadius: 6, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${(a.c / max) * 100}%`, background: isUn ? "var(--coral)" : "var(--gold)", borderRadius: 6 }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* recent */}
      <div style={card}>
        <div className="panel-pad" style={{ paddingBottom: 0 }}><div className="panel-title">🕑 Recent leads</div></div>
        <table>
          <thead><tr><th>Lead</th><th>Source</th><th>City</th><th>Society</th><th>Stage</th><th>Owner</th><th>Received</th></tr></thead>
          <tbody>
            {data.recent.map((l) => (
              <tr key={l.id} className="lead-row" onClick={() => nav(`/leads/${l.id}`)}>
                <td><div className="who"><div className="av">{initials(l.name)}</div><div className="nm">{l.name}</div></div></td>
                <td><span className={`src ${srcClass(l.source)}`}>{srcLabel(l.source)}</span></td>
                <td style={{ fontSize: 12.5 }}>{l.city || "—"}</td>
                <td style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{l.society || "—"}</td>
                <td><span className={`stage ${stageClass(l.stage)}`}>{stageLabel(l.stage)}</span></td>
                <td style={{ fontSize: 12.5 }}>{l.assigned_to || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                <td style={{ fontSize: 12, fontFamily: "'Spline Sans Mono'", color: "var(--muted)" }}>{formatDate(l.received_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
