/* Follow-up — the callback worklist. Any non-terminal lead with an open follow-up
   lands here (not-connected + saved-not-qualified live ONLY here; qualified leads
   also appear as a due reminder). Rows are gated: Yes logs a connected call and opens
   the lead, No reschedules +3h (10 misses on a never-reached lead → RNR). */
import { useState } from "react";
import { useLeads } from "../lib/queries";
import { Lead } from "../lib/api";
import { srcClass, srcLabel, initials } from "../lib/leads";
import { useSearch, matches } from "../components/SearchContext";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { useSort, SortTh } from "../lib/useSort";
import { CallConnected } from "../components/CallConnected";
import { NotesCell } from "../components/NotesCell";
import { AssignControl } from "../components/AssignControl";

// follow-up due → friendly label + overdue/soon class
function DueChip({ at }: { at: string | null }) {
  if (!at) return <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>;
  const mins = Math.round((new Date(at).getTime() - Date.now()) / 60000);
  const label = new Date(at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  let cls = "", suffix = "";
  if (mins < 0) { cls = " overdue"; suffix = ` · ${Math.abs(mins) >= 60 ? Math.round(Math.abs(mins) / 60) + "h" : Math.abs(mins) + "m"} late`; }
  else if (mins < 60) { cls = " soon"; suffix = ` · in ${mins}m`; }
  return <span className={`fu-chip${cls}`}>⏰ {label}{suffix}</span>;
}

export default function Followup() {
  const { data, isLoading } = useLeads("followup");
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
      matches(query, l.name, l.phone, l.city, l.society, srcLabel(l.source))
  );
  // default order = backend's soonest-due-first; columns can re-sort
  const { sorted: list, sortKey, dir, onSort } = useSort<Lead>(filtered, {
    name: (l) => l.name,
    due: (l) => (l.follow_up_at ? Date.parse(l.follow_up_at) : null),
    misses: (l) => l.miss_count,
    assigned: (l) => l.assigned_to,
    society: (l) => l.society,
  });

  return (
    <>
      <div className="section-head">
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{filtered.length !== all.length ? `${filtered.length} of ${all.length}` : all.length}</b>{" "}
          callbacks due · soonest first. Log every attempt — <b style={{ color: "var(--emerald)" }}>Yes</b> opens the lead, <b style={{ color: "var(--coral)" }}>No</b> reschedules +3h.
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
        <table>
          <thead>
            <tr>
              <SortTh label="Lead" sortKey="name" activeKey={sortKey} dir={dir} onSort={onSort} />
              <th>Call connected?</th>
              <SortTh label="Follow-up due" sortKey="due" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Misses" sortKey="misses" activeKey={sortKey} dir={dir} onSort={onSort} />
              <th>Stage</th>
              <SortTh label="Society" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Assigned" sortKey="assigned" activeKey={sortKey} dir={dir} onSort={onSort} />
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={8}><div className="empty" style={{ padding: 30 }}>Loading…</div></td></tr>
            ) : list.length === 0 ? (
              <tr><td colSpan={8}><div className="empty" style={{ padding: 30 }}>
                {all.length === 0 ? "No callbacks scheduled right now. 🎉" : "No leads match the search / filters."}
              </div></td></tr>
            ) : (
              list.map((l) => (
                <tr key={l.id} className="lead-row" style={{ cursor: "default" }}>
                  <td>
                    <div className="who">
                      <div className="av">{initials(l.name)}</div>
                      <div>
                        <div className="nm">{l.name}{l.is_test && <span className="bucket-tag" style={{ marginLeft: 6 }}>TEST</span>}</div>
                        <div className="ph">{l.phone}</div>
                      </div>
                    </div>
                  </td>
                  <td><CallConnected leadId={l.id} /></td>
                  <td><DueChip at={l.follow_up_at} /></td>
                  <td>
                    {l.miss_count > 0
                      ? <span className={"miss-chip" + (l.miss_count >= 5 ? " hot" : "")}>{l.miss_count} miss</span>
                      : <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>}
                  </td>
                  <td>
                    {l.confirmed
                      ? <span className="stage won">Qualified</span>
                      : <span className={`src ${srcClass(l.source)}`}>{srcLabel(l.source)}</span>}
                  </td>
                  <td style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{l.society || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                  <td onClick={(e) => e.stopPropagation()}><AssignControl leadId={l.id} assignedTo={l.assigned_to} /></td>
                  <td onClick={(e) => e.stopPropagation()}><NotesCell leadId={l.id} latest={l.latest_note} count={l.note_count} /></td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
