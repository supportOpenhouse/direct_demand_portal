/* Qualified / Pipeline / Converted leads — 1:1 with the prototype's tplLeads()
   table (Lead · Source · Stage · TAT · Society · Assigned · Visits). Same component
   for all three segments, switched by the `segment` prop. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLeads } from "../lib/queries";
import { Lead } from "../lib/api";
import { srcClass, srcLabel, stageClass, stageLabel, initials } from "../lib/leads";
import { useSearch, matches } from "../components/SearchContext";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { useSort, SortTh } from "../lib/useSort";
import { useToast } from "../components/Toast";
import { WhatsAppIcon } from "../components/icons";
import { AssignControl } from "../components/AssignControl";
import { waChat } from "../lib/whatsapp";
import { VisitPlanner } from "../features/VisitPlanner";

const SUBS: Record<string, string> = {
  qualified: "Confirmed on call, within 7 days of qualifying. After 7 days a lead auto-moves to Pipeline.",
  pipeline: "Qualified leads that have aged 7+ days in the funnel — still active.",
  converted: "Won — token received.",
};
const NOUN: Record<string, string> = { qualified: "qualified leads", pipeline: "pipeline leads", converted: "converted leads" };

// minutes from a TAT deadline → the prototype's ok/warn/breach chip (null → —)
function TatChip({ deadline }: { deadline: string | null }) {
  if (!deadline) return <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>;
  const mins = Math.round((new Date(deadline).getTime() - Date.now()) / 60000);
  if (mins < 0) return <span className="tat breach">⚠ {Math.abs(mins)}m over</span>;
  if (mins < 30) return <span className="tat warn">{mins}m left</span>;
  return <span className="tat ok">{mins}m left</span>;
}

export default function LeadsSegment({ segment }: { segment: "qualified" | "pipeline" | "converted" }) {
  const { data, isLoading } = useLeads(segment);
  const nav = useNavigate();
  const toast = useToast();
  const { query } = useSearch();
  const [source, setSource] = useState("");
  const [city, setCity] = useState("");
  const [planner, setPlanner] = useState<Lead | null>(null);

  const all = data?.items ?? [];
  const filtered = all.filter(
    (l) =>
      (!source || l.source === source) &&
      (!city || l.city === city) &&
      matches(query, l.name, l.phone, l.city, l.society, srcLabel(l.source), stageLabel(l.stage))
  );
  const { sorted: list, sortKey, dir, onSort } = useSort<Lead>(filtered, {
    name: (l) => l.name,
    source: (l) => srcLabel(l.source),
    stage: (l) => stageLabel(l.stage),
    tat: (l) => (l.tat_deadline ? Date.parse(l.tat_deadline) : null),
    society: (l) => l.society,
    assigned: (l) => l.assigned_to,
  });

  return (
    <>
      <div className="section-head">
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{filtered.length !== all.length ? `${filtered.length} of ${all.length}` : all.length}</b>{" "}
          {NOUN[segment]} · {SUBS[segment]}
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <FilterSelect label="Source" value={source} options={uniqueValues(all, (l) => l.source).map(srcLabel)}
            onChange={(v) => setSource(uniqueValues(all, (l) => l.source).find((s) => srcLabel(s) === v) || "")} width={140} />
          <FilterSelect label="City" value={city} options={uniqueValues(all, (l) => l.city)} onChange={setCity} width={130} />
        </div>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <SortTh label="Lead" sortKey="name" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Source" sortKey="source" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Stage" sortKey="stage" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="TAT" sortKey="tat" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Society" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Assigned" sortKey="assigned" activeKey={sortKey} dir={dir} onSort={onSort} />
              <th></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={7}><div className="empty" style={{ padding: 30 }}>Loading…</div></td></tr>
            ) : list.length === 0 ? (
              <tr><td colSpan={7}><div className="empty" style={{ padding: 30 }}>
                {all.length === 0 ? `No ${NOUN[segment]} yet.` : "No leads match the search / filters."}
              </div></td></tr>
            ) : (
              list.map((l) => (
                <tr key={l.id} className="lead-row" onClick={() => nav(`/leads/${l.id}`)}>
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
                  <td><span className={`stage ${stageClass(l.stage)}`}>{stageLabel(l.stage)}</span></td>
                  <td><TatChip deadline={l.tat_deadline} /></td>
                  <td style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{l.society || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                  <td onClick={(e) => e.stopPropagation()}><AssignControl leadId={l.id} assignedTo={l.assigned_to} /></td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                      <button className="wa-ico" title={`WhatsApp ${l.name}`}
                        onClick={(e) => { e.stopPropagation(); l.phone ? waChat(l.phone) : toast("No phone number", "gold", "⚠"); }}>
                        <WhatsAppIcon />
                      </button>
                      <button className="btn ghost sm" title="Plan site visits"
                        onClick={(e) => { e.stopPropagation(); setPlanner(l); }}>
                        📅 Visits
                      </button>
                    </span>
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
