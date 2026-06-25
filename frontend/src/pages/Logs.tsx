/* Activity Logs — admin audit trail of every meaningful action with its actor.
   Server records writes + logins + lead views via the audit middleware. */
import { useState } from "react";
import { useLogs, useLogActors, formatDateTime } from "../lib/queries";
import { AuditLogRow } from "../lib/api";
import { FilterSelect } from "../components/Filters";
import { useDebounce } from "../lib/useDebounce";
import { initials } from "../lib/leads";

const PAGE = 50;
const CATEGORIES = ["auth", "write", "read"];
const METHODS = ["GET", "POST", "PATCH", "DELETE"];

function catChip(cat: string) {
  const map: Record<string, [string, string]> = {
    auth: ["var(--blue-soft)", "var(--blue)"],
    write: ["var(--emerald-soft)", "#06694b"],
    read: ["var(--slate-soft)", "var(--slate)"],
  };
  const [bg, fg] = map[cat] || ["var(--slate-soft)", "var(--slate)"];
  return <span className="cfg-chip" style={{ background: bg, color: fg }}>{cat}</span>;
}

function statusColor(s: number | null): string {
  if (s == null) return "var(--muted)";
  if (s >= 500) return "var(--coral)";
  if (s >= 400) return "var(--amber)";
  return "var(--emerald)";
}

export default function Logs() {
  const [actor, setActor] = useState("");
  const [category, setCategory] = useState("");
  const [method, setMethod] = useState("");
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(0);
  const dq = useDebounce(q, 300);

  const params = {
    actor: actor || undefined,
    category: category || undefined,
    method: method || undefined,
    q: dq || undefined,
    from: from || undefined,
    to: to ? `${to}T23:59:59` : undefined,
    limit: PAGE,
    offset: page * PAGE,
  };
  const { data, isLoading, isFetching } = useLogs(params);
  const { data: actors } = useLogActors();

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const start = total === 0 ? 0 : page * PAGE + 1;
  const end = Math.min(total, (page + 1) * PAGE);
  const reset = (fn: () => void) => { fn(); setPage(0); };
  const anyFilter = actor || category || method || q || from || to;

  return (
    <>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <p className="sec-sub" style={{ margin: 0 }}>
          Every action taken in the portal, with the actor and result.{" "}
          <b style={{ color: "var(--ink-2)" }}>{total.toLocaleString("en-IN")}</b> events{isFetching ? " · updating…" : ""}
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <FilterSelect label="Who" value={actor} options={actors?.items ?? []} onChange={(v) => reset(() => setActor(v))} width={170} />
          <FilterSelect label="Type" value={category} options={CATEGORIES} onChange={(v) => reset(() => setCategory(v))} width={110} />
          <FilterSelect label="Method" value={method} options={METHODS} onChange={(v) => reset(() => setMethod(v))} width={120} />
          <input className="pick-ctrl" type="date" value={from} onChange={(e) => reset(() => setFrom(e.target.value))} title="From date" style={{ padding: "7px 9px", fontSize: 12.5 }} />
          <input className="pick-ctrl" type="date" value={to} onChange={(e) => reset(() => setTo(e.target.value))} title="To date" style={{ padding: "7px 9px", fontSize: 12.5 }} />
          <div className="field" style={{ marginBottom: 0, width: 190 }}>
            <input value={q} placeholder="Search action / path…" onChange={(e) => reset(() => setQ(e.target.value))} style={{ padding: "7px 10px", fontSize: 12.5 }} />
          </div>
          {anyFilter && (
            <button className="btn ghost sm" onClick={() => { setActor(""); setCategory(""); setMethod(""); setQ(""); setFrom(""); setTo(""); setPage(0); }}>
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="card panel-pad">
        <table>
          <thead>
            <tr>
              <th style={{ width: 150 }}>When</th>
              <th>Actor</th>
              <th>Action</th>
              <th style={{ width: 90 }}>Method</th>
              <th>Path</th>
              <th style={{ width: 70 }}>Status</th>
              <th style={{ width: 70 }}>Time</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={7}><div className="empty" style={{ padding: 24 }}>Loading logs…</div></td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={7}><div className="empty" style={{ padding: 24 }}>{anyFilter ? "No events match these filters." : "No activity logged yet."}</div></td></tr>
            ) : (
              items.map((l: AuditLogRow) => (
                <tr key={l.id}>
                  <td style={{ fontSize: 12, whiteSpace: "nowrap", fontFamily: "'Spline Sans Mono'" }}>{formatDateTime(l.created_at)}</td>
                  <td>
                    <div className="who">
                      <div className="av" style={{ width: 26, height: 26, fontSize: 10 }}>{initials(l.actor_name || l.actor_email)}</div>
                      <div style={{ minWidth: 0 }}>
                        <div className="nm" style={{ fontSize: 12.5 }}>{l.actor_name || l.actor_email || "—"}</div>
                        {l.actor_role && <div className="ph" style={{ fontSize: 10.5, textTransform: "capitalize" }}>{l.actor_role}</div>}
                      </div>
                    </div>
                  </td>
                  <td style={{ fontSize: 12.5 }}>{l.action} {catChip(l.category)}</td>
                  <td><span className="cfg-chip" style={{ fontFamily: "'Spline Sans Mono'", fontSize: 11 }}>{l.method}</span></td>
                  <td style={{ fontSize: 11.5, color: "var(--muted)", fontFamily: "'Spline Sans Mono'", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={l.path}>{l.path}</td>
                  <td style={{ fontWeight: 700, color: statusColor(l.status_code), fontFamily: "'Spline Sans Mono'", fontSize: 12.5 }}>{l.status_code ?? "—"}</td>
                  <td style={{ fontSize: 11.5, color: "var(--muted)" }}>{l.duration_ms != null ? `${l.duration_ms}ms` : "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
          <span style={{ fontSize: 12, color: "var(--muted)" }}>
            {total > 0 ? `${start}–${end} of ${total.toLocaleString("en-IN")}` : "—"}
          </span>
          <span style={{ display: "flex", gap: 6 }}>
            <button className="btn ghost sm" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>← Prev</button>
            <button className="btn ghost sm" disabled={end >= total} onClick={() => setPage((p) => p + 1)}>Next →</button>
          </span>
        </div>
      </div>
    </>
  );
}
