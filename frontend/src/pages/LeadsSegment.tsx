/* Qualified / Pipeline / Converted leads — 1:1 with the prototype's tplLeads()
   table (Lead · Source · Stage · TAT · Society · Assigned · Visits). Same component
   for all three segments, switched by the `segment` prop. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLeads, formatDate, useMarkHot } from "../lib/queries";
import { Lead } from "../lib/api";
import { srcClass, srcLabel, stageClass, stageLabel, initials, leadMatchesQuery } from "../lib/leads";
import { useSearch } from "../components/SearchContext";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { useSort, SortTh } from "../lib/useSort";
import { ExportCsvButton } from "../components/ExportCsvButton";
import { useRowSelection } from "../lib/useRowSelection";
import { BulkAssignBar } from "../components/BulkAssignBar";
import { NotesCell } from "../components/NotesCell";
import { VisitsCell } from "../components/VisitsCell";
import { AssignControl } from "../components/AssignControl";
import { VisitPlanner } from "../features/VisitPlanner";

const NOUN: Record<string, string> = { qualified: "qualified leads", pipeline: "pipeline leads", converted: "converted leads", rejected: "rejected leads" };

// minutes from a TAT deadline → the prototype's ok/warn/breach chip (null → —)
function TatChip({ deadline }: { deadline: string | null }) {
  if (!deadline) return <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>;
  const mins = Math.round((new Date(deadline).getTime() - Date.now()) / 60000);
  if (mins < 0) return <span className="tat breach">⚠ {Math.abs(mins)}m over</span>;
  if (mins < 30) return <span className="tat warn">{mins}m left</span>;
  return <span className="tat ok">{mins}m left</span>;
}

// ★ toggle — marks a lead hot (Pipeline filter uses it)
function HotStar({ lead }: { lead: Lead }) {
  const mark = useMarkHot();
  return (
    <button
      className={"hot-star" + (lead.is_hot ? " on" : "")}
      title={lead.is_hot ? "Unmark as hot" : "Mark as hot"}
      disabled={mark.isPending}
      onClick={(e) => { e.stopPropagation(); mark.mutate({ id: lead.id, hot: !lead.is_hot }); }}
    >
      {lead.is_hot ? "★" : "☆"}
    </button>
  );
}

export default function LeadsSegment({ segment }: { segment: "qualified" | "pipeline" | "converted" | "rejected" }) {
  const rejected = segment === "rejected";
  const pipeline = segment === "pipeline";
  const { data, isLoading } = useLeads(segment);
  const nav = useNavigate();
  const { query } = useSearch();
  const [source, setSource] = useState("");
  const [city, setCity] = useState("");
  const [owner, setOwner] = useState("");
  const [hotOnly, setHotOnly] = useState(false);
  const [visitStatus, setVisitStatus] = useState("");
  const [planner, setPlanner] = useState<Lead | null>(null);

  const all = data?.items ?? [];
  const filtered = all.filter(
    (l) =>
      (!source || l.source === source) &&
      (!city || l.city === city) &&
      (!owner || (owner === "Unassigned" ? !l.assigned_to : l.assigned_to === owner)) &&
      (!hotOnly || l.is_hot) &&
      (!visitStatus || l.visit_status === visitStatus) &&
      leadMatchesQuery(query, l)
  );
  const { sorted: list, sortKey, dir, onSort } = useSort<Lead>(filtered, {
    name: (l) => l.name,
    source: (l) => srcLabel(l.source),
    stage: (l) => stageLabel(l.stage),
    tat: (l) => (l.tat_deadline ? Date.parse(l.tat_deadline) : null),
    society: (l) => l.society,
    assigned: (l) => l.assigned_to,
    reason: (l) => l.reject_reason,
    rejected: (l) => (l.rejected_at ? Date.parse(l.rejected_at) : null),
    notes: (l) => (l.latest_note_at ? Date.parse(l.latest_note_at) : null),
    visit: (l) => l.visit_status,
  });
  const sel = useRowSelection(list.map((l) => l.id));

  return (
    <>
      <div className="section-head">
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{filtered.length !== all.length ? `${filtered.length} of ${all.length}` : all.length}</b>{" "}
          {NOUN[segment]}
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <FilterSelect label="Source" value={source} options={uniqueValues(all, (l) => l.source).map(srcLabel)}
            onChange={(v) => setSource(uniqueValues(all, (l) => l.source).find((s) => srcLabel(s) === v) || "")} width={130} />
          <FilterSelect label="City" value={city} options={uniqueValues(all, (l) => l.city)} onChange={setCity} width={120} />
          <FilterSelect label="Owner" value={owner} options={["Unassigned", ...uniqueValues(all, (l) => l.assigned_to)]} onChange={setOwner} width={140} />
          {pipeline && (
            <>
              <FilterSelect label="Visit" value={visitStatus} options={["upcoming", "completed", "cancelled"]} onChange={setVisitStatus} width={130} />
              <button
                className={"btn sm " + (hotOnly ? "" : "ghost")}
                style={hotOnly ? { background: "var(--coral)", color: "#fff" } : undefined}
                onClick={() => setHotOnly((v) => !v)}
                title="Show only leads starred as hot"
              >
                ★ Hot only{hotOnly ? ` (${filtered.length})` : ""}
              </button>
            </>
          )}
          {(source || city || owner || hotOnly || visitStatus) && (
            <button className="btn ghost sm" onClick={() => { setSource(""); setCity(""); setOwner(""); setHotOnly(false); setVisitStatus(""); }}>Clear</button>
          )}
          <ExportCsvButton leads={list} name={segment} />
        </div>
      </div>

      <BulkAssignBar ids={sel.activeIds} onDone={sel.clear} />

      <div className="card">
        <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 30 }}>
                <input type="checkbox" checked={sel.allChecked} onChange={sel.toggleAll} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} title="Select all" />
              </th>
              {pipeline && <th style={{ width: 34 }} title="Hot">★</th>}
              <SortTh label="Lead" sortKey="name" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Source" sortKey="source" activeKey={sortKey} dir={dir} onSort={onSort} />
              {rejected ? (
                <>
                  <SortTh label="Reason" sortKey="reason" activeKey={sortKey} dir={dir} onSort={onSort} />
                  <th>Reject note</th>
                  <SortTh label="Rejected" sortKey="rejected" activeKey={sortKey} dir={dir} onSort={onSort} />
                </>
              ) : (
                <>
                  <SortTh label="Stage" sortKey="stage" activeKey={sortKey} dir={dir} onSort={onSort} />
                  <SortTh label="TAT" sortKey="tat" activeKey={sortKey} dir={dir} onSort={onSort} />
                  <SortTh label="Society" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
                </>
              )}
              <SortTh label="Notes" sortKey="notes" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Assigned" sortKey="assigned" activeKey={sortKey} dir={dir} onSort={onSort} />
              <th></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={pipeline ? 10 : 9}><div className="empty" style={{ padding: 30 }}>Loading…</div></td></tr>
            ) : list.length === 0 ? (
              <tr><td colSpan={pipeline ? 10 : 9}><div className="empty" style={{ padding: 30 }}>
                {all.length === 0 ? `No ${NOUN[segment]} yet.` : "No leads match the search / filters."}
              </div></td></tr>
            ) : (
              list.map((l) => (
                <tr key={l.id} className="lead-row" onClick={() => nav(`/leads/${l.id}`)}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={sel.has(l.id)} onChange={() => sel.toggle(l.id)} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} />
                  </td>
                  {pipeline && <td onClick={(e) => e.stopPropagation()}><HotStar lead={l} /></td>}
                  <td>
                    <div className="who">
                      <div className="av">{initials(l.name)}</div>
                      <div>
                        <div className="nm">{l.name}{l.is_test && <span className="bucket-tag" style={{ marginLeft: 6 }}>TEST</span>}</div>
                        <div className="ph">{l.phone}</div>
                      </div>
                    </div>
                  </td>
                  <td><span className={`src ${srcClass(l.source)}`}>{srcLabel(l.source)}</span></td>
                  {rejected ? (
                    <>
                      <td><span className="stage lost">{l.reject_reason || "—"}</span></td>
                      <td style={{ fontSize: 12.5, color: "var(--ink-2)", maxWidth: 280, whiteSpace: "normal" }}>{l.reject_notes || "—"}</td>
                      <td style={{ fontSize: 12, fontFamily: "'Spline Sans Mono'", color: "var(--muted)", whiteSpace: "nowrap" }}>{l.rejected_at ? formatDate(l.rejected_at) : "—"}</td>
                    </>
                  ) : (
                    <>
                      <td>{l.visit_status
                        ? <VisitsCell leadId={l.id} status={l.visit_status} date={l.visit_date} count={l.visit_count} />
                        : <span className={`stage ${stageClass(l.stage)}`}>{stageLabel(l.stage)}</span>}</td>
                      <td><TatChip deadline={l.tat_deadline} /></td>
                      <td style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{l.society || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                    </>
                  )}
                  <td onClick={(e) => e.stopPropagation()}><NotesCell leadId={l.id} latest={l.latest_note} count={l.note_count} /></td>
                  <td onClick={(e) => e.stopPropagation()}><AssignControl leadId={l.id} assignedTo={l.assigned_to} /></td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {!rejected && (
                      <button className="btn ghost sm" title="Plan site visits"
                        onClick={(e) => { e.stopPropagation(); setPlanner(l); }}>
                        📅 Visits
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>
      </div>
      {planner && (
        <VisitPlanner leadId={planner.id} leadName={planner.name} leadCity={planner.city} leadPhone={planner.phone} onClose={() => setPlanner(null)} />
      )}
    </>
  );
}
