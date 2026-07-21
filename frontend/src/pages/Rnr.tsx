/* RNR (Ring No Response) — terminal bucket. A never-connected lead that missed 10
   consecutive calls lands here, like Rejected. Read-only review list (click to open). */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLeads, formatDate } from "../lib/queries";
import { Lead } from "../lib/api";
import { srcClass, srcLabel, initials, leadMatchesQuery } from "../lib/leads";
import { useSearch } from "../components/SearchContext";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { useSort, SortTh } from "../lib/useSort";
import { AssignControl } from "../components/AssignControl";

export default function Rnr() {
  const { data, isLoading } = useLeads("rnr");
  const nav = useNavigate();
  const { query } = useSearch();
  const [source, setSource] = useState("");
  const [city, setCity] = useState("");
  const [owner, setOwner] = useState("");

  const all = data?.items ?? [];
  const filtered = all.filter(
    (l) =>
      (!source || l.source === source) &&
      (!city || l.city === city) &&
      (!owner || (owner === "Unassigned" ? !l.assigned_to : l.assigned_to === owner)) &&
      leadMatchesQuery(query, l)
  );
  const { sorted: list, sortKey, dir, onSort } = useSort<Lead>(filtered, {
    name: (l) => l.name,
    source: (l) => srcLabel(l.source),
    misses: (l) => l.miss_count,
    city: (l) => l.city,
    society: (l) => l.society,
    assigned: (l) => l.assigned_to,
  });

  return (
    <>
      <div className="section-head">
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{filtered.length !== all.length ? `${filtered.length} of ${all.length}` : all.length}</b>{" "}
          unreachable leads
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

      <div className="card">
        <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <SortTh label="Lead" sortKey="name" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Source" sortKey="source" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Missed calls" sortKey="misses" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="City" sortKey="city" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Society" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Assigned" sortKey="assigned" activeKey={sortKey} dir={dir} onSort={onSort} />
              <th>First seen</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={7}><div className="empty" style={{ padding: 30 }}>Loading…</div></td></tr>
            ) : list.length === 0 ? (
              <tr><td colSpan={7}><div className="empty" style={{ padding: 30 }}>
                {all.length === 0 ? "No unreachable leads. 🎉" : "No leads match the search / filters."}
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
                  <td><span className="miss-chip hot">{l.miss_count} missed</span></td>
                  <td style={{ fontSize: 12.5 }}>{l.city || "—"}</td>
                  <td style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{l.society || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                  <td onClick={(e) => e.stopPropagation()}><AssignControl leadId={l.id} assignedTo={l.assigned_to} /></td>
                  <td style={{ fontSize: 12, fontFamily: "'Spline Sans Mono'", color: "var(--muted)", whiteSpace: "nowrap" }}>{formatDate(l.received_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>
      </div>
    </>
  );
}
