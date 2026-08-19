/* Activity log — what changed, who changed it, and from what to what.

   The previous version of this page listed HTTP requests: "POST /v1/leads/{id}/confirm
   · 200 · 45ms". That told you a request happened, not what it did — you couldn't
   answer "who moved this lead to rejected and why", which is the only question anyone
   opens this page with.

   The Details column is the whole point: each action renders as a sentence, not as
   three raw columns the reader has to assemble in their head. */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useActivity, useActivityFilters, formatDateTime } from "../lib/queries";
import { ActivityRow, api } from "../lib/api";
import { FilterSelect } from "../components/Filters";
import { useDebounce } from "../lib/useDebounce";

const PAGE = 100;
const pretty = (v: string) => v.replace(/_/g, " ");

/* Colour by consequence, not by verb: the reader is scanning for "did something bad
   happen to a lead", so a rejection and a lost call read the same way. */
const GOOD = new Set(["stage_change_qualified", "call_connected", "marked_hot", "assigned"]);
const BAD = new Set(["call_missed", "unmarked_hot"]);

function actionStyle(r: ActivityRow) {
  if (r.action === "stage_change") {
    const to = r.after_value || "";
    if (["won", "qualified", "visit_scheduled", "revisit_scheduled"].includes(to))
      return { background: "var(--emerald-soft)", color: "#06694b" };
    if (["rejected", "rnr"].includes(to))
      return { background: "var(--coral-soft)", color: "var(--coral)" };
    return { background: "var(--amber-soft)", color: "var(--amber)" };
  }
  if (GOOD.has(r.action)) return { background: "var(--emerald-soft)", color: "#06694b" };
  if (BAD.has(r.action)) return { background: "var(--coral-soft)", color: "var(--coral)" };
  return { background: "var(--panel-2)", color: "var(--ink-2)" };
}

/* One sentence per action. Falls through to a generic field diff, so an action added
   later still renders something useful rather than a blank cell. */
function Details({ r }: { r: ActivityRow }) {
  const m = (r.metadata || {}) as Record<string, any>;
  const val = (v: string | null) => v ?? "—";

  switch (r.action) {
    case "stage_change":
      return (
        <>
          <b>{val(r.before_value)}</b> → <b>{val(r.after_value)}</b>
          {m.reason && <span className="lg-sub"> · {m.reason}</span>}
          {m.notes && <span className="lg-sub"> — {m.notes}</span>}
        </>
      );
    case "assigned":
      return r.after_value
        ? <>to <b>{r.after_value}</b>{r.before_value && <span className="lg-sub"> (was {r.before_value})</span>}
            {m.bulk && <span className="lg-sub"> · part of a {m.bulk}-lead bulk assign</span>}</>
        : <>unassigned{r.before_value && <span className="lg-sub"> (was {r.before_value})</span>}</>;
    case "note_added":
      return <span className="lg-note">“{m.note}”</span>;
    case "call_connected":
      return <>reached them<span className="lg-sub"> · {m.source === "campaign" ? "auto-dialer" : "worklist"}</span></>;
    case "call_missed":
      return (
        <>
          {m.reason || "not reached"}
          <span className="lg-sub"> · miss {val(r.after_value)}</span>
          {m.follow_up_at && <span className="lg-sub"> · retry {formatDateTime(m.follow_up_at)}</span>}
          {m.notes && <span className="lg-sub"> — {m.notes}</span>}
        </>
      );
    case "marked_hot":   return <>starred as hot</>;
    case "unmarked_hot": return <>no longer hot</>;
    case "sync_run":
      return <>{Object.entries(m).map(([k, v]) => `${k}: ${v}`).join(" · ") || "ran"}</>;
    default:
      // generic: a field diff if there is one, else whatever context was recorded
      if (r.field) return <><b>{r.field}</b>: {val(r.before_value)} → {val(r.after_value)}</>;
      return <span className="lg-sub">{Object.keys(m).length ? JSON.stringify(m) : "—"}</span>;
  }
}

export default function Logs() {
  const [q, setQ] = useState("");
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [actor, setActor] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(0);
  const [exporting, setExporting] = useState(false);
  const dq = useDebounce(q, 300);

  const filters = useActivityFilters().data;
  const params = {
    q: dq || undefined, action: action || undefined,
    entity_type: entityType || undefined, actor: actor || undefined,
    from: from || undefined, to: to || undefined,
  };
  const { data, isLoading, isFetching } = useActivity({ ...params, limit: PAGE, offset: page * PAGE });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const start = total === 0 ? 0 : page * PAGE + 1;
  const end = Math.min(total, (page + 1) * PAGE);
  const reset = (fn: () => void) => { fn(); setPage(0); };
  const anyFilter = q || action || entityType || actor || from || to;


  return (
    <>
      <div className="section-head lg-head">
        <div className="lg-counts">
          <div><b>{total.toLocaleString("en-IN")}</b> events{isFetching && <span className="lg-sub"> · updating…</span>}</div>
        </div>
        <div className="lg-filters">
          <FilterSelect label="Action" value={action} width={170}
            options={(filters?.actions ?? []).map((a: string) => ({ value: a, label: pretty(a) }))}
            onChange={(v) => reset(() => setAction(v))} />
          <FilterSelect label="Type" value={entityType} width={130}
            options={filters?.entity_types ?? []} onChange={(v) => reset(() => setEntityType(v))} />
          <FilterSelect label="Who" value={actor} width={190}
            options={filters?.actors ?? []} onChange={(v) => reset(() => setActor(v))} />
          <input type="date" className="lg-date" value={from} title="From (IST)"
            onChange={(e) => reset(() => setFrom(e.target.value))} />
          <input type="date" className="lg-date" value={to} title="To (IST)"
            onChange={(e) => reset(() => setTo(e.target.value))} />
          <div className="field lg-search">
            <input value={q} placeholder="Search actor / lead / value…"
              onChange={(e) => reset(() => setQ(e.target.value))} />
          </div>
          {anyFilter && (
            <button className="btn ghost sm" onClick={() => reset(() => {
              setQ(""); setAction(""); setEntityType(""); setActor(""); setFrom(""); setTo("");
            })}>Clear</button>
          )}
          <button className="btn sm" disabled={exporting}
            onClick={() => { setExporting(true); api.activityExport(params).finally(() => setExporting(false)); }}>
            {exporting ? "Exporting…" : "↓ CSV"}
          </button>
        </div>
      </div>

      <div className="card table-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 150 }}>When</th>
              <th style={{ width: 160 }}>Who</th>
              <th style={{ width: 160 }}>What</th>
              <th style={{ width: 180 }}>On</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5}><div className="empty" style={{ padding: 24 }}>Loading…</div></td></tr>
            ) : !items.length ? (
              <tr><td colSpan={5}><div className="empty" style={{ padding: 24 }}>
                {anyFilter ? "No activity matches these filters." : "No activity recorded yet."}
              </div></td></tr>
            ) : items.map((r) => (
              <tr key={r.id}>
                <td style={{ fontSize: 12, whiteSpace: "nowrap", fontFamily: "'Spline Sans Mono'" }}>
                  {formatDateTime(r.created_at)}
                </td>
                <td style={{ fontSize: 12.5 }}>
                  {/* A background job has no actor — saying "system" is truer than blank */}
                  {r.actor_name || r.actor_email || <span className="lg-sub">system</span>}
                  {r.actor_role && <div className="lg-sub">{r.actor_role}</div>}
                </td>
                <td>
                  <span className="cfg-chip" style={actionStyle(r)}>{pretty(r.action)}</span>
                </td>
                <td style={{ fontSize: 12.5 }}>
                  {/* Link straight to the lead — this page is usually the first step of
                      "what happened to X", and the second step is opening X. */}
                  {r.entity_type === "lead" && r.entity_id ? (
                    <Link className="lead-link" to={`/leads/${r.entity_id}`}>
                      {r.lead_name || "lead"}
                    </Link>
                  ) : (
                    <>{r.entity_type}{r.entity_id && <span className="lg-sub"> · {r.entity_id}</span>}</>
                  )}
                </td>
                <td style={{ fontSize: 12.5 }}><Details r={r} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {total > PAGE && (
        <div className="lg-pager">
          <span className="lg-sub">{start}–{end} of {total.toLocaleString("en-IN")}</span>
          <button className="btn ghost sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
          <button className="btn ghost sm" disabled={end >= total} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      )}
    </>
  );
}
