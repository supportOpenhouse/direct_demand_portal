/* Per-RM report.

   Every number comes from activity_log, so a column is only ever as good as the event
   behind it — which is why the instrumentation went in first. Nothing here reads the
   leads table: counting `stage = 'qualified'` would give you the current state, not
   who moved it or when, and a lead qualified last month would land in today's column.

   Zero rows are the point. An RM with a blank line is the finding a manager opens this
   page for, so they're rendered as muted zeroes rather than hidden. */
import { useState } from "react";
import { useRmReport } from "../lib/queries";
/* Presets, metric columns and the detail link are shared with ReportDetail — see
   lib/report.ts on why they can't live on either page. */
import { COLUMNS, detailHref, hhmm, PRESETS, Preset, rangeFor, todayIST } from "../lib/report";

function Num({ n, strong }: { n: number; strong?: boolean }) {
  // A zero is information, not an absence — muted, never blank.
  return (
    <td className={"rp-num" + (n === 0 ? " zero" : "") + (strong ? " strong" : "")}>
      {n.toLocaleString("en-IN")}
    </td>
  );
}

export default function Reports() {
  const [preset, setPreset] = useState<Preset>("today");
  const [from, setFrom] = useState(todayIST);
  const [to, setTo] = useState(todayIST);
  const { data, isLoading, isFetching } = useRmReport(from, to, preset === "all");

  const pick = (p: Preset) => {
    setPreset(p);
    // Custom keeps whatever range was already on screen, so switching to it is a
    // starting point rather than a reset.
    if (p !== "custom" && p !== "all") {
      const [f, t] = rangeFor(p);
      setFrom(f); setTo(t);
    }
  };

  const rows = data?.items ?? [];
  /* "Login" is the first activity of the IST day. Over a multi-day range that's the
     first activity of the FIRST day, which reads like a clock-in time and isn't one —
     so the column only fills in when the range is a single day, and the drill-down
     carries the per-day times for every other range. Read off the server's echoed
     range, because All resolves its floor there. */
  const singleDay = data ? data.from === data.to : from === to;
  const totals = COLUMNS.reduce((acc, c) => {
    acc[c.key] = rows.reduce((n, r) => n + r[c.key], 0);
    return acc;
  }, {} as Record<string, number>);
  const worked = rows.filter((r) => r.total_events > 0).length;

  return (
    <>
      <div className="section-head rp-head">
        <div className="rp-counts">
          <div><b>{rows.length}</b> RMs</div>
          {/* the interesting half of the headline: how many actually did anything */}
          <div className="rp-sub">
            {worked} active ·{" "}
            {/* The server resolves All from the log's first row, so echo what came
                back rather than what was asked for. */}
            {data ? (data.from === data.to ? data.from : `${data.from} → ${data.to}`) : "…"}
          </div>
        </div>
        <div className="rp-filters">
          <div className="rp-presets" role="group" aria-label="Date range">
            {PRESETS.map((p) => (
              <button key={p.key}
                className={"rp-pill" + (preset === p.key ? " on" : "")}
                onClick={() => pick(p.key)}>
                {p.label}
              </button>
            ))}
          </div>
          {isFetching && <span className="rp-sub">updating…</span>}
          {/* Only Custom gets the inputs — for every other preset they'd be a
              read-only echo of the pill already highlighted. Rendered last and
              full-width so selecting Custom ADDS a line under the pills instead of
              widening the row and shoving everything beside it around. One unit, too:
              half a range on each line would read as two ranges. */}
          {preset === "custom" && (
            <span className="rp-range">
              <input type="date" className="rp-date" value={from} title="From (IST)"
                onChange={(e) => setFrom(e.target.value)} />
              <span className="rp-sub">→</span>
              <input type="date" className="rp-date" value={to} title="To (IST)"
                onChange={(e) => setTo(e.target.value)} />
            </span>
          )}
        </div>
      </div>

      <div className="card table-wrap">
        <table className="tbl rp-tbl">
          <thead>
            <tr>
              <th style={{ width: 200 }}>RM</th>
              <th style={{ width: 90 }} title={singleDay
                ? "First activity of the day, IST — not the login event: a week-long session means someone can work for days without signing in"
                : "Only shown for a single-day range — open an RM to see their login for each day"}>
                Login
              </th>
              {COLUMNS.map((c) => (
                <th key={c.key} className="rp-th" title={c.hint}>{c.label}</th>
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
              const href = detailHref(r.email, preset, from, to);
              return (
                /* The whole row opens the report — the numbers are what a manager is
                   reading, so the name isn't a better click target than the count next
                   to it. The anchor below stays anyway: a row can't BE a link, and
                   dropping it would take middle-click, copy-link and keyboard focus
                   with it. It stops propagation so the two don't both fire. */
                <tr key={r.email}
                    className={"rp-row" + (r.total_events === 0 ? " rp-idle" : "")}
                    onClick={() => window.open(href, "_blank", "noopener")}
                    title={`Open ${r.name || r.email}'s day-by-day report in a new tab`}>
                  <td>
                    {/* A plain anchor with target=_blank, not a react-router Link:
                        the detail page reads its whole range out of the querystring,
                        so the new tab is a real, reloadable, shareable URL. */}
                    <a className="rp-rm" target="_blank" rel="noreferrer" href={href}
                       onClick={(e) => e.stopPropagation()}>
                      <div style={{ fontSize: 13 }}>{r.name || r.email}</div>
                      <div className="rp-sub">{r.email}
                        {r.role === "test_rm" && <span className="dl-testtag">TEST</span>}
                      </div>
                    </a>
                  </td>
                  <td className="rp-num">
                    {singleDay
                      ? (login || <span className="rp-sub">—</span>)
                      : <span className="rp-sub" title="Multi-day range — open the RM for per-day logins">—</span>}
                  </td>
                  {COLUMNS.map((c) => (
                    <Num key={c.key} n={r[c.key]}
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
                  <Num key={c.key} n={totals[c.key]}
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
        Click any row to open that RM's day-by-day report in a new tab.
      </p>
    </>
  );
}
