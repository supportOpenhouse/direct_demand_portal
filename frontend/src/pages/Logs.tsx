/* Activity log — what changed, who changed it, and from what to what.

   The previous version of this page listed HTTP requests: "POST /v1/leads/{id}/confirm
   · 200 · 45ms". That told you a request happened, not what it did — you couldn't
   answer "who moved this lead to rejected and why", which is the only question anyone
   opens this page with.

   The Details column is the whole point: each action renders as a sentence, not as
   three raw columns the reader has to assemble in their head. */
import { useState } from "react";
import { useActivity, useActivityFilters, formatDateTime } from "../lib/queries";
import { ActivityRow, api } from "../lib/api";
import { FilterSelect } from "../components/Filters";
import { useDebounce } from "../lib/useDebounce";
import { SkeletonTable } from "../components/Skeleton";
import { FilterBar, useFilterValues } from "../components/FilterBar";
import { LeadLink } from "../components/LeadModal";
import { actionStyle, Details, pretty } from "../lib/activity";
import { ExportFieldsModal } from "../components/ExportFieldsModal";

const PAGE = 100;

export default function Logs() {
  const [q, setQ] = useState("");
  const { values: f, set, clear } = useFilterValues({ action: "", entityType: "", actor: "", from: "", to: "" });
  const { action, entityType, actor, from, to } = f;
  const [page, setPage] = useState(0);
  const [exporting, setExporting] = useState(false);
  // the CSV button opens a column picker first; the download runs from inside it
  const [picking, setPicking] = useState(false);
  const dq = useDebounce(q, 300);

  const filters = useActivityFilters().data;
  const params = {
    q: dq || undefined, action: action || undefined,
    entity_type: entityType || undefined, actor: actor || undefined,
    from: from || undefined, to: to || undefined,
  };
  const { data, isLoading, isFetching, isPlaceholderData } = useActivity({ ...params, limit: PAGE, offset: page * PAGE });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const start = total === 0 ? 0 : page * PAGE + 1;
  const end = Math.min(total, (page + 1) * PAGE);
  const reset = (fn: () => void) => { fn(); setPage(0); };
  const anyFilter = q || action || entityType || actor || from || to;
  // keepPreviousData holds the LAST query's rows while a new filter loads — reading them
  // as the answer is the mistake, so a changed query shows the skeleton instead.
  const loading = isLoading || isPlaceholderData;


  return (
    <>
      <div className="section-head lg-head">
        <div className="lg-counts">
          <div>{loading ? <span className="lg-sub">Loading…</span> : <><b>{total.toLocaleString("en-IN")}</b> events</>}{isFetching && !loading && <span className="lg-sub"> · updating…</span>}</div>
        </div>
        <div className="lg-filters">
          <FilterBar
            fields={[
              { key: "action", label: "Action",
                options: (filters?.actions ?? []).map((a: string) => ({ value: a, label: pretty(a) })) },
              { key: "entityType", label: "Type", options: filters?.entity_types ?? [] },
              { key: "actor", label: "Who", options: filters?.actors ?? [] },
              { key: "from", label: "From (IST)", kind: "date" },
              { key: "to", label: "To (IST)", kind: "date" },
            ]}
            values={f}
            onChange={(k, v) => reset(() => set(k, v))}
            onClear={() => reset(clear)}
          />
          <div className="field lg-search">
            <input value={q} placeholder="Search actor / lead / value…"
              onChange={(e) => reset(() => setQ(e.target.value))} />
          </div>
          {anyFilter && (
            <button className="btn ghost sm" onClick={() => reset(() => {
              setQ(""); clear();
            })}>Clear</button>
          )}
          <button className="btn sm" disabled={exporting} onClick={() => setPicking(true)}>
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
            {loading ? (
              <SkeletonTable rows={8} cols={5} />
            ) : !items.length ? (
              <tr><td colSpan={5}><div className="empty" style={{ padding: 24 }}>
                {anyFilter ? "No activity matches these filters." : "No activity recorded yet."}
              </div></td></tr>
            ) : items.map((r) => (
              <tr key={r.id}>
                <td style={{ fontSize: 12, whiteSpace: "nowrap", fontFamily: "var(--font-mono)" }}>
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
                    <LeadLink className="lead-link" id={r.entity_id}>
                      {r.lead_name || "lead"}
                    </LeadLink>
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
      {picking && (
        <ExportFieldsModal busy={exporting} onClose={() => setPicking(false)}
          onExport={(fields) => {
            setExporting(true);
            api.activityExport(params, fields)
              .then(() => setPicking(false))
              .finally(() => setExporting(false));
          }} />
      )}
    </>
  );
}
