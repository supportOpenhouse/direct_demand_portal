/* Qualified / Pipeline / Converted leads — 1:1 with the prototype's tplLeads()
   table (Lead · Source · Stage · TAT · Society · Assigned · Visits). Same component
   for all three segments, switched by the `segment` prop. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLeads, formatDate } from "../lib/queries";
import { Lead } from "../lib/api";
import { srcClass, srcLabel, stageClass, stageLabel, initials } from "../lib/leads";
import { useSearch, matches } from "../components/SearchContext";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { useSort, SortTh } from "../lib/useSort";
import { useRowSelection } from "../lib/useRowSelection";
import { BulkAssignBar } from "../components/BulkAssignBar";
import { NotesCell } from "../components/NotesCell";
import { AssignControl } from "../components/AssignControl";
import { VisitPlanner } from "../features/VisitPlanner";

const SUBS: Record<string, string> = {
  qualified: "Confirmed on call, within 7 days of qualifying. After 7 days a lead auto-moves to Pipeline.",
  pipeline: "Qualified leads that have aged 7+ days in the funnel — still active.",
  converted: "Won — token received.",
  rejected: "Leads rejected with a reason and notes.",
};
const NOUN: Record<string, string> = { qualified: "qualified leads", pipeline: "pipeline leads", converted: "converted leads", rejected: "rejected leads" };

// minutes from a TAT deadline → the prototype's ok/warn/breach chip (null → —)
function TatChip({ deadline }: { deadline: string | null }) {
  if (!deadline) return <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>;
  const mins = Math.round((new Date(deadline).getTime() - Date.now()) / 60000);
  if (mins < 0) return <span className="tat breach">⚠ {Math.abs(mins)}m over</span>;
  if (mins < 30) return <span className="tat warn">{mins}m left</span>;
  return <span className="tat ok">{mins}m left</span>;
}

export default function LeadsSegment({ segment }: { segment: "qualified" | "pipeline" | "converted" | "rejected" }) {
  const rejected = segment === "rejected";
  const { data, isLoading } = useLeads(segment);
  const nav = useNavigate();
  const { query } = useSearch();
  const [source, setSource] = useState("");
  const [city, setCity] = useState("");
  const [owner, setOwner] = useState("");
  const [planner, setPlanner] = useState<Lead | null>(null);

  const all = data?.items ?? [];
  const filtered = all.filter(
    (l) =>
      (!source || l.source === source) &&
      (!city || l.city === city) &&
      (!owner || (owner === "Unassigned" ? !l.assigned_to : l.assigned_to === owner)) &&
      matches(query, l.name, l.phone, l.city, l.society, srcLabel(l.source), stageLabel(l.stage))
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
  });
  const sel = useRowSelection(list.map((l) => l.id));

  return (
    <>
      <div className="section-head">
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{filtered.length !== all.length ? `${filtered.length} of ${all.length}` : all.length}</b>{" "}
          {NOUN[segment]} · {SUBS[segment]}
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <FilterSelect label="Source" value={source} options={uniqueValues(all, (l) => l.source).map(srcLabel)}
            onChange={(v) => setSource(uniqueValues(all, (l) => l.source).find((s) => srcLabel(s) === v) || "")} width={130} />
          <FilterSelect label="City" value={city} options={uniqueValues(all, (l) => l.city)} onChange={setCity} width={120} />
          <FilterSelect label="Owner" value={owner} options={["Unassigned", ...uniqueValues(all, (l) => l.assigned_to)]} onChange={setOwner} width={140} />
          {(source || city || owner) && (
            <button className="btn ghost sm" onClick={() => { setSource(""); setCity(""); setOwner(""); }}>Clear</button>
          )}
        </div>
      </div>

      <BulkAssignBar ids={sel.activeIds} onDone={sel.clear} />

      <div className="card">
        <table>
          <thead>
            <tr>
              <th style={{ width: 30 }}>
                <input type="checkbox" checked={sel.allChecked} onChange={sel.toggleAll} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} title="Select all" />
              </th>
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
              <tr><td colSpan={9}><div className="empty" style={{ padding: 30 }}>Loading…</div></td></tr>
            ) : list.length === 0 ? (
              <tr><td colSpan={9}><div className="empty" style={{ padding: 30 }}>
                {all.length === 0 ? `No ${NOUN[segment]} yet.` : "No leads match the search / filters."}
              </div></td></tr>
            ) : (
              list.map((l) => (
                <tr key={l.id} className="lead-row" onClick={() => nav(`/leads/${l.id}`)}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={sel.has(l.id)} onChange={() => sel.toggle(l.id)} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} />
                  </td>
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
                      <td><span className={`stage ${stageClass(l.stage)}`}>{stageLabel(l.stage)}</span></td>
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
      {planner && (
        <VisitPlanner leadId={planner.id} leadName={planner.name} leadCity={planner.city} onClose={() => setPlanner(null)} />
      )}
    </>
  );
}
