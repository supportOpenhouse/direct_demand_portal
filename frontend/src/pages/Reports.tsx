/* Per-RM report.

   Every number comes from activity_log, so a column is only ever as good as the event
   behind it — which is why the instrumentation went in first. Nothing here reads the
   leads table: counting `stage = 'qualified'` would give you the current state, not
   who moved it or when, and a lead qualified last month would land in today's column.

   Zero rows are the point. An RM with a blank line is the finding a manager opens this
   page for, so they're rendered as muted zeroes rather than hidden. */
import { useState } from "react";
import { useRmReport } from "../lib/queries";
import { RmReportRow } from "../lib/api";

const IST = "Asia/Kolkata";
const todayIST = () =>
  new Date(Date.now() + 330 * 60_000).toISOString().slice(0, 10);

/* Only the time — the date is already the page's range, and repeating it in every
   row would crowd out the numbers. */
const hhmm = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString("en-IN",
    { timeZone: IST, hour: "2-digit", minute: "2-digit", hour12: false }) : null;

const COLUMNS: { key: keyof RmReportRow; label: string; hint: string }[] = [
  { key: "calls_dialled",   label: "Dialled",   hint: "Connected + Missed, as marked by the RM" },
  { key: "calls_connected", label: "Connected", hint: "Marked 'Yes' on a call" },
  { key: "calls_missed",    label: "Missed",    hint: "Marked 'No', with a reason" },
  { key: "leads_qualified", label: "Qualified", hint: "Stage moved to qualified" },
  { key: "visit_scheduled", label: "Visit",     hint: "Stage moved to visit_scheduled" },
  { key: "revisit_booked",  label: "Revisit",   hint: "Stage moved to revisit_scheduled" },
  { key: "leads_rejected",  label: "Rejected",  hint: "Stage moved to rejected" },
];

function Num({ n, strong }: { n: number; strong?: boolean }) {
  // A zero is information, not an absence — muted, never blank.
  return (
    <td className={"rp-num" + (n === 0 ? " zero" : "") + (strong ? " strong" : "")}>
      {n.toLocaleString("en-IN")}
    </td>
  );
}

export default function Reports() {
  const [from, setFrom] = useState(todayIST);
  const [to, setTo] = useState(todayIST);
  const { data, isLoading, isFetching } = useRmReport(from, to);

  const rows = data?.items ?? [];
  const totals = COLUMNS.reduce((acc, c) => {
    acc[c.key as string] = rows.reduce((n, r) => n + (r[c.key] as number), 0);
    return acc;
  }, {} as Record<string, number>);
  const worked = rows.filter((r) => r.total_events > 0).length;

  const preset = (days: number) => {
    const end = todayIST();
    const start = new Date(Date.now() + 330 * 60_000 - days * 864e5).toISOString().slice(0, 10);
    setFrom(days === 0 ? end : start);
    setTo(end);
  };

  return (
    <>
      <div className="section-head rp-head">
        <div className="rp-counts">
          <div><b>{rows.length}</b> RMs</div>
          {/* the interesting half of the headline: how many actually did anything */}
          <div className="rp-sub">{worked} active in this range</div>
        </div>
        <div className="rp-filters">
          <button className="btn ghost sm" onClick={() => preset(0)}>Today</button>
          <button className="btn ghost sm" onClick={() => preset(6)}>7 days</button>
          <button className="btn ghost sm" onClick={() => preset(29)}>30 days</button>
          <input type="date" className="rp-date" value={from} title="From (IST)"
            onChange={(e) => setFrom(e.target.value)} />
          <span className="rp-sub">→</span>
          <input type="date" className="rp-date" value={to} title="To (IST)"
            onChange={(e) => setTo(e.target.value)} />
          {isFetching && <span className="rp-sub">updating…</span>}
        </div>
      </div>

      <div className="card table-wrap">
        <table className="tbl rp-tbl">
          <thead>
            <tr>
              <th style={{ width: 200 }}>RM</th>
              <th style={{ width: 90 }} title="First activity of the day, IST — not the login event: a week-long session means someone can work for days without signing in">
                Login
              </th>
              {COLUMNS.map((c) => (
                <th key={c.key as string} className="rp-th" title={c.hint}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={COLUMNS.length + 2}>
                <div className="empty" style={{ padding: 24 }}>Loading…</div></td></tr>
            ) : !rows.length ? (
              <tr><td colSpan={COLUMNS.length + 2}>
                <div className="empty" style={{ padding: 24 }}>No RMs to report on.</div></td></tr>
            ) : rows.map((r) => {
              const login = hhmm(r.first_action_at);
              return (
                <tr key={r.email} className={r.total_events === 0 ? "rp-idle" : ""}>
                  <td>
                    <div style={{ fontSize: 13 }}>{r.name || r.email}</div>
                    <div className="rp-sub">{r.email}
                      {r.role === "test_rm" && <span className="dl-testtag">TEST</span>}
                    </div>
                  </td>
                  <td className="rp-num">
                    {login || <span className="rp-sub">—</span>}
                  </td>
                  {COLUMNS.map((c) => (
                    <Num key={c.key as string} n={r[c.key] as number}
                         strong={c.key === "calls_dialled"} />
                  ))}
                </tr>
              );
            })}
          </tbody>
          {rows.length > 0 && (
            <tfoot>
              <tr className="rp-total">
                <td>Total</td>
                <td />
                {COLUMNS.map((c) => (
                  <Num key={c.key as string} n={totals[c.key as string]}
                       strong={c.key === "calls_dialled"} />
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      <p className="rp-note">
        Counts are derived from the activity log, so they begin when an event type was
        first recorded — earlier work isn't attributable to a person and doesn't appear.
      </p>
    </>
  );
}
