/* One RM's report, day by day — the drill-down behind a row on /reports.

   The summary table collapses a range into a single line per person, which answers
   "how much" and nothing else. The question a manager actually has next is "on which
   days, and on which leads" — so this page splits the same metrics by IST day, and
   each day opens the leads that produced its numbers.

   Layout follows the other dashboard's per-user report: a day list you scan, a modal
   you open. Nothing new is measured here; every number is the same activity_log
   predicate the summary table uses, which is why they reconcile. */
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useRmDayLeads, useRmReportDays } from "../lib/queries";
import { RmDayLeadRow, RmDayRow } from "../lib/api";
import { COLUMNS, dayLabel, hhmm, PRESETS, Preset, rangeFor, todayIST } from "../lib/report";
import { downloadCsv } from "../lib/csv";
import { stageClass, stageLabel } from "../lib/leads";

/* A day's numbers as pills. Every metric is rendered even at zero — a day with four
   qualifieds and no calls is a different day from one with neither, and hiding the
   zeroes makes the two rows the same length and hard to compare down the column. */
function Pills({ row }: { row: RmDayRow }) {
  return (
    <div className="rd-pills">
      {COLUMNS.map((c) => (
        <span key={c.key} className={"rd-pill" + (row[c.key] === 0 ? " zero" : "")} title={c.hint}>
          {c.label} <b>{row[c.key]}</b>
        </span>
      ))}
    </div>
  );
}

function Stage({ s }: { s: string | null }) {
  if (!s) return <span className="rp-sub">—</span>;
  return <span className={`stage ${stageClass(s)}`}>{stageLabel(s)}</span>;
}

/* The leads behind one day's numbers.

   `from → to` is the day's own journey (first `before`, last `after`), not the lead's
   whole history — a lead moved twice in a morning shows where it started and where it
   ended, and the steps between are in the lead's own timeline. "Now" is deliberately
   the only live value on the row: when it disagrees with `to`, someone moved the lead
   again after this day, which is worth seeing. */
function DayLeads({ email, day, onClose }: { email: string; day: string; onClose: () => void }) {
  const { data, isLoading, error } = useRmDayLeads(email, day);
  const items = data?.items ?? [];

  const exportCsv = () =>
    downloadCsv(
      `report-${email.replace(/[^a-z0-9]+/gi, "_")}-${day}.csv`,
      ["Time", "Lead", "Phone", "City", "Dialled", "Connected", "Missed", "From", "To", "Now", "Note"],
      items.map((l) => [
        hhmm(l.last_at) ?? "", l.name ?? "", l.phone ?? "", l.city ?? "",
        l.calls_dialled, l.calls_connected, l.calls_missed,
        l.from_stage ? stageLabel(l.from_stage) : "",
        l.to_stage ? stageLabel(l.to_stage) : "",
        l.current_stage ? stageLabel(l.current_stage) : "",
        l.note ?? "",
      ]),
    );

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal wide rd-modal">
        <div className="mh">
          <h3>{dayLabel(day)}</h3>
          <div className="rd-modal-actions">
            <span className="rp-sub">{items.length} lead{items.length === 1 ? "" : "s"}</span>
            <button className="btn ghost sm" onClick={exportCsv} disabled={!items.length}>⬇ Export CSV</button>
            <button className="btn ghost sm" onClick={onClose}>Close</button>
          </div>
        </div>
        <div className="mb">
          {isLoading ? <div className="empty" style={{ padding: 24 }}>Loading…</div>
            : error ? <div className="empty" style={{ padding: 24 }}>Couldn’t load this day.</div>
            : !items.length ? <div className="empty" style={{ padding: 24 }}>No leads touched on this day.</div>
            : (
              <div className="table-wrap">
                <table className="tbl rd-tbl">
                  <thead>
                    <tr>
                      <th style={{ width: 60 }}>Time</th>
                      <th>Lead</th>
                      <th style={{ width: 100 }}>City</th>
                      <th className="rp-th" title="Connected + Missed on this lead, this day">Dialled</th>
                      <th className="rp-th">Conn.</th>
                      <th className="rp-th">Missed</th>
                      <th style={{ width: 300 }}>Stage moved</th>
                      <th style={{ width: 130 }} title="The lead's stage right now — differs from 'to' if it moved again later">Now</th>
                      <th>Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((l: RmDayLeadRow) => (
                      <tr key={l.lead_id ?? "unlinked"}>
                        <td className="rp-num">{hhmm(l.last_at) ?? "—"}</td>
                        <td>
                          {/* Only linked when the join actually landed. A lead can be
                              deleted after it was worked, and some rows carry no
                              entity_id at all — both keep their counts (or the modal
                              stops adding up to the day row) but neither has a page. */}
                          {l.lead_id && l.name
                            ? <Link to={`/leads/${l.lead_id}`} target="_blank" className="rd-lead-link">{l.name}</Link>
                            : <span className="rp-sub">{l.lead_id ? "deleted lead" : "no lead linked"}</span>}
                          {l.source && <div className="rp-sub">{l.source}</div>}
                        </td>
                        <td>{l.city || <span className="rp-sub">—</span>}</td>
                        <td className={"rp-num" + (l.calls_dialled === 0 ? " zero" : "")}>{l.calls_dialled}</td>
                        <td className={"rp-num" + (l.calls_connected === 0 ? " zero" : "")}>{l.calls_connected}</td>
                        <td className={"rp-num" + (l.calls_missed === 0 ? " zero" : "")}>{l.calls_missed}</td>
                        <td>
                          {l.to_stage
                            ? <span className="rd-move"><Stage s={l.from_stage} /> → <Stage s={l.to_stage} /></span>
                            : <span className="rp-sub">no stage change</span>}
                        </td>
                        <td>
                          {l.current_stage && l.current_stage === l.to_stage
                            ? <span className="rp-sub">same</span>
                            : <Stage s={l.current_stage} />}
                        </td>
                        <td className="rd-note">
                          {l.note ? <span title={l.note}>{l.note}</span> : <span className="rp-sub">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        </div>
      </div>
    </div>
  );
}

export default function ReportDetail() {
  const [params] = useSearchParams();
  const email = (params.get("email") || "").toLowerCase();
  /* The range arrives in the URL so the tab is a shareable, reloadable link — the
     page it was opened from is in another tab and can't be asked. */
  const initialAll = params.get("all") === "true";
  const [preset, setPreset] = useState<Preset>(initialAll ? "all" : "custom");
  const [from, setFrom] = useState(params.get("from") || todayIST());
  const [to, setTo] = useState(params.get("to") || todayIST());

  const { data, isLoading, isFetching } = useRmReportDays(email, from, to, preset === "all");
  const days = data?.days ?? [];

  const pick = (p: Preset) => {
    setPreset(p);
    if (p !== "custom" && p !== "all") {
      const [f, t] = rangeFor(p);
      setFrom(f); setTo(t);
    }
  };

  const totals = {
    actions: days.reduce((n, d) => n + d.total_events, 0),
    // Summed, not distinct: the same lead worked on two days is two days of work.
    // The honest cross-day figure would need its own query, and this page is about
    // days.
    leads: days.reduce((n, d) => n + d.unique_leads, 0),
  };

  const exportCsv = () =>
    downloadCsv(
      `report-${email.replace(/[^a-z0-9]+/gi, "_")}-${data?.from}-to-${data?.to}.csv`,
      ["Date", "Login", "Actions", "Leads", ...COLUMNS.map((c) => c.label)],
      days.map((d) => [d.day, hhmm(d.first_action_at) ?? "", d.total_events, d.unique_leads,
                       ...COLUMNS.map((c) => d[c.key])]),
    );

  const [openDay, setOpenDay] = useState<string | null>(null);

  if (!email) return <div className="empty" style={{ padding: 24 }}>No RM in the link.</div>;

  return (
    <>
      <div className="section-head rp-head">
        <div className="rp-counts">
          <div>
            <b>{data?.name || email}</b>
            {data?.role === "test_rm" && <span className="dl-testtag">TEST</span>}
          </div>
          <div className="rp-sub">{email}</div>
          <div className="rp-sub">
            {days.length} active day{days.length === 1 ? "" : "s"} · {totals.leads} leads ·{" "}
            {totals.actions} actions ·{" "}
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
          {preset === "custom" && (
            <>
              <input type="date" className="rp-date" value={from} title="From (IST)"
                onChange={(e) => setFrom(e.target.value)} />
              <span className="rp-sub">→</span>
              <input type="date" className="rp-date" value={to} title="To (IST)"
                onChange={(e) => setTo(e.target.value)} />
            </>
          )}
          <button className="btn ghost sm" onClick={exportCsv} disabled={!days.length}>⬇ Export CSV</button>
          {isFetching && <span className="rp-sub">updating…</span>}
        </div>
      </div>

      {isLoading ? (
        <div className="card"><div className="empty" style={{ padding: 24 }}>Loading…</div></div>
      ) : !days.length ? (
        <div className="card">
          <div className="empty" style={{ padding: 24 }}>
            Nothing logged in this range.
          </div>
        </div>
      ) : (
        <div className="rd-days">
          {days.map((d) => (
            <button key={d.day} className="rd-day card" onClick={() => setOpenDay(d.day)}>
              <div className="rd-day-head">
                <div className="rd-day-date">{dayLabel(d.day)}</div>
                <div className="rd-day-meta">
                  {/* Here — unlike the summary table — "Login" is a real clock-in:
                      the row is exactly one day, so the first action of the range and
                      the first action of the day are the same thing. */}
                  <span title="First activity of this day, IST">
                    login <b>{hhmm(d.first_action_at) ?? "—"}</b>
                  </span>
                  <span title="Last activity of this day, IST">
                    last <b>{hhmm(d.last_action_at) ?? "—"}</b>
                  </span>
                  <span><b>{d.unique_leads}</b> leads</span>
                  <span><b>{d.total_events}</b> actions</span>
                </div>
              </div>
              <Pills row={d} />
            </button>
          ))}
        </div>
      )}

      {openDay && <DayLeads email={email} day={openDay} onClose={() => setOpenDay(null)} />}

      <p className="rp-note">
        Days with no logged activity have no row — the summary table on{" "}
        <Link to="/reports">Reports</Link> is where an idle RM shows up.
      </p>
    </>
  );
}
