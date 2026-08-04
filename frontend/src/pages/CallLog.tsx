/* Bonvoice Call Log — every call leg Bonvoice has reported, with its recording.
   A bridged call is two rows: leg A rings the RM's handset, leg B dials the lead. */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCallLog, useSyncCallLog, formatDateTime } from "../lib/queries";
import { CallLogRow } from "../lib/api";
import { FilterSelect } from "../components/Filters";
import { useToast } from "../components/Toast";
import { useDebounce } from "../lib/useDebounce";

const PAGE = 50;
const ANSWERED = ["Connected", "Not connected"];

const ymd = (d: Date) => d.toISOString().slice(0, 10);

function duration(row: CallLogRow): string {
  if (!row.start_at || !row.end_at) return "—";
  const secs = Math.round((+new Date(row.end_at) - +new Date(row.start_at)) / 1000);
  if (secs < 0) return "—";
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}

export default function CallLog() {
  const [q, setQ] = useState("");
  const [conn, setConn] = useState("");
  const [page, setPage] = useState(0);
  const dq = useDebounce(q, 300);
  const toast = useToast();

  // Backfill window — last 30 days by default, which is the usual "why isn't that
  // call here?" range. Bonvoice holds the full history if you widen it.
  const [from, setFrom] = useState(() => ymd(new Date(Date.now() - 30 * 864e5)));
  const [to, setTo] = useState(() => ymd(new Date()));
  const sync = useSyncCallLog();
  const runSync = () => sync.mutate({ from, to }, {
    onSuccess: (r) => toast(`Synced ${r.stored} of ${r.fetched} call records`, "green", "✓"),
    onError: (e: any) => toast(e.message, "gold", "⚠"),
  });

  const { data, isLoading, isFetching } = useCallLog({
    q: dq || undefined,
    answered: conn ? conn === "Connected" : undefined,
    limit: PAGE,
    offset: page * PAGE,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const start = total === 0 ? 0 : page * PAGE + 1;
  const end = Math.min(total, (page + 1) * PAGE);
  const reset = (fn: () => void) => { fn(); setPage(0); };
  const anyFilter = q || conn;

  return (
    <>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{total.toLocaleString("en-IN")}</b> call legs{isFetching ? " · updating…" : ""}
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <FilterSelect label="Outcome" value={conn} options={ANSWERED} onChange={(v) => reset(() => setConn(v))} width={150} />
          <div className="field" style={{ marginBottom: 0, width: 220 }}>
            <input value={q} placeholder="Search phone (any format) / lead name…" onChange={(e) => reset(() => setQ(e.target.value))} style={{ padding: "7px 10px", fontSize: 12.5 }} />
          </div>
          {anyFilter && (
            <button className="btn ghost sm" onClick={() => { setQ(""); setConn(""); setPage(0); }}>Clear</button>
          )}
          <span style={{ width: 1, height: 22, background: "var(--line)" }} />
          <input className="pick-ctrl" type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} title="Sync from" style={{ padding: "7px 9px", fontSize: 12.5 }} />
          <input className="pick-ctrl" type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} title="Sync to" style={{ padding: "7px 9px", fontSize: 12.5 }} />
          <button className="btn sm" onClick={runSync} disabled={sync.isPending}
                  title="Pull Bonvoice's own call records for this date range">
            {sync.isPending ? "Syncing…" : "Sync from Bonvoice"}
          </button>
        </div>
      </div>

      <div className="card panel-pad">
        <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 150 }}>When</th>
              <th>Lead</th>
              <th style={{ width: 46 }}>Leg</th>
              <th>From → To</th>
              <th>Status</th>
              <th style={{ width: 70 }}>Duration</th>
              <th style={{ width: 250 }}>Recording</th>
              <th>Placed by</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={8}><div className="empty" style={{ padding: 24 }}>Loading calls…</div></td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={8}><div className="empty" style={{ padding: 24 }}>{anyFilter ? "No calls match these filters." : "No calls logged yet."}</div></td></tr>
            ) : (
              items.map((c) => (
                <tr key={`${c.call_id}-${c.leg}`}>
                  <td style={{ fontSize: 12, whiteSpace: "nowrap", fontFamily: "'Spline Sans Mono'" }}>{formatDateTime(c.start_at) || "—"}</td>
                  <td style={{ fontSize: 12.5 }}>
                    {c.lead_id ? <Link to={`/leads/${c.lead_id}`}>{c.lead_name || "View lead"}</Link> : <span style={{ color: "var(--muted)" }}>—</span>}
                  </td>
                  <td><span className="cfg-chip">{c.leg}</span></td>
                  <td style={{ fontSize: 12, fontFamily: "'Spline Sans Mono'", whiteSpace: "nowrap" }}>
                    {c.source_number || "—"} → {c.destination_number || "—"}
                  </td>
                  <td style={{ fontSize: 12.5 }}>
                    <span className="cfg-chip" style={{
                      background: c.answered ? "var(--emerald-soft)" : "var(--slate-soft)",
                      color: c.answered ? "#06694b" : "var(--slate)",
                    }}>
                      {c.answered ? "connected" : "not connected"}
                    </span>{" "}
                    <span style={{ color: "var(--muted)", fontSize: 11.5 }}>{c.status || c.agent_status || ""}</span>
                  </td>
                  <td style={{ fontSize: 12, fontFamily: "'Spline Sans Mono'" }}>{duration(c)}</td>
                  <td>
                    {/* ponytail: the native player streams Bonvoice's ResourceURL straight
                        from their CDN — proxy it through the API only if it starts 401ing */}
                    {c.recording_url ? (
                      <audio controls preload="none" src={c.recording_url} style={{ height: 32, width: 240 }} />
                    ) : <span style={{ color: "var(--muted)" }}>—</span>}
                  </td>
                  <td style={{ fontSize: 12, color: "var(--muted)" }}>{c.placed_by || "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>

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
