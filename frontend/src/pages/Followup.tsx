/* The callback worklist, used by two pages:

     Follow Up          (stage='follow_up')        — we've spoken to them, callback due
     Call Not Received  (stage='call_not_received') — called, never yet reached

   Same columns and same actions, so it's one component with a segment prop rather
   than two near-identical files. Rows are gated: Yes logs a connected call and opens
   the lead, No asks why and reschedules accordingly (10 misses on a never-reached
   lead → RNR; an invalid number → Rejected). */
import { useState } from "react";
import { useLeads } from "../lib/queries";
import { Lead } from "../lib/api";
import { srcClass, srcLabel, leadMatchesQuery } from "../lib/leads";
import { useSearch } from "../components/SearchContext";
import { FilterSelect, uniqueValues, countedOptions, matchesOption, DateFilter, inDatePreset, type DatePreset } from "../components/Filters";
import { useSort, SortTh } from "../lib/useSort";
import { ExportCsvButton } from "../components/ExportCsvButton";
import { useRowSelection } from "../lib/useRowSelection";
import { BulkAssignBar } from "../components/BulkAssignBar";
import { CallConnected } from "../components/CallConnected";
import { NotesCell } from "../components/NotesCell";
import { AssignControl } from "../components/AssignControl";
import { CallButton } from "../components/CallButton";
import LeadPhone from "../components/LeadPhone";

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

// same calendar day as now (local)
const isToday = (iso: string | null): boolean => {
  if (!iso) return false;
  const d = new Date(iso), n = new Date();
  return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate();
};

export default function Followup({ segment = "followup" }: { segment?: string } = {}) {
  const { data, isLoading } = useLeads(segment);
  const { query } = useSearch();
  const [source, setSource] = useState("");
  const [city, setCity] = useState("");
  const [owner, setOwner] = useState("");
  const [datePreset, setDatePreset] = useState<DatePreset>("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const all = data?.items ?? [];
  const filtered = all.filter(
    (l) =>
      (!source || l.source === source) &&
      matchesOption(l.city, city) &&
      matchesOption(l.assigned_to, owner) &&
      inDatePreset(l.follow_up_at, datePreset, dateFrom, dateTo) &&
      leadMatchesQuery(query, l)
  );
  /* Default order mirrors the row highlights, most-actionable first:
       0 green    — moved into Follow-up today
       1 blue     — follow-up due today
       2 overdue  — due before today, latest → oldest (freshest misses first)
       3 upcoming — due later, soonest first
     Picking a column header still overrides all of this. */
  const dayStart = new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate()).getTime();
  const rank = (l: Lead): number => {
    if (isToday(l.follow_up_since)) return 0;
    if (isToday(l.follow_up_at)) return 1;
    const t = l.follow_up_at ? Date.parse(l.follow_up_at) : null;
    return t !== null && t < dayStart ? 2 : 3;
  };
  const ordered = [...filtered].sort((a, b) => {
    const ra = rank(a), rb = rank(b);
    if (ra !== rb) return ra - rb;
    const ta = a.follow_up_at ? Date.parse(a.follow_up_at) : 0;
    const tb = b.follow_up_at ? Date.parse(b.follow_up_at) : 0;
    return ra === 2 ? tb - ta : ta - tb; // overdue: latest first · others: soonest first
  });
  const { sorted: list, sortKey, dir, onSort } = useSort<Lead>(ordered, {
    name: (l) => l.name,
    due: (l) => (l.follow_up_at ? Date.parse(l.follow_up_at) : null),
    misses: (l) => l.miss_count,
    assigned: (l) => l.assigned_to,
    society: (l) => l.society,
  });
  const sel = useRowSelection(list.map((l) => l.id));

  return (
    <>
      <div className="section-head">
        <div>
          <p className="sec-sub" style={{ margin: 0 }}>
            <b style={{ color: "var(--ink-2)" }}>{filtered.length !== all.length ? `${filtered.length} of ${all.length}` : all.length}</b>{" "}
            callbacks
          </p>
          <div style={{ display: "flex", gap: 14, alignItems: "center", marginTop: 6, fontSize: 11.5, color: "var(--muted)" }}>
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 10, height: 10, borderRadius: 3, background: "var(--emerald-soft)", border: "1px solid #aedcc4" }} /> moved here today
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 10, height: 10, borderRadius: 3, background: "var(--blue-soft)", border: "1px solid #b9d0fb" }} /> follow-up due today
            </span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <FilterSelect label="Source" value={source}
            options={uniqueValues(all, (l) => l.source).map((s) => ({ value: s, label: srcLabel(s) }))}
            onChange={setSource} width={130} />
          <FilterSelect label="City" value={city} options={countedOptions(all, (l) => l.city, "No City")} onChange={setCity} width={150} />
          <FilterSelect label="Owner" value={owner} options={countedOptions(all, (l) => l.assigned_to, "Unassigned")} onChange={setOwner} width={160} />
          <DateFilter label="Due" preset={datePreset} from={dateFrom} to={dateTo} onPreset={setDatePreset} onFrom={setDateFrom} onTo={setDateTo} />
          {(source || city || owner || datePreset) && (
            <button className="btn ghost sm" onClick={() => { setSource(""); setCity(""); setOwner(""); setDatePreset(""); setDateFrom(""); setDateTo(""); }}>Clear</button>
          )}
          <ExportCsvButton leads={list} name="follow-up" />
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
              <SortTh label="Lead" sortKey="name" activeKey={sortKey} dir={dir} onSort={onSort} />
              <th>Call connected?</th>
              <SortTh label="Follow-up due" sortKey="due" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Misses" sortKey="misses" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Society" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Assigned To" sortKey="assigned" activeKey={sortKey} dir={dir} onSort={onSort} />
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
                <tr
                  key={l.id}
                  /* green (arrived in Follow-up today) takes priority over blue (due today) */
                  className={"lead-row" + (isToday(l.follow_up_since) ? " fu-arrived" : isToday(l.follow_up_at) ? " fu-due" : "")}
                  style={{ cursor: "default" }}
                >
                  <td onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={sel.has(l.id)} onChange={() => sel.toggle(l.id)} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} />
                  </td>
                  <td>
                    <div className="who">
                      <CallButton leadId={l.id} disabled={!l.phone} />
                      <div>
                        <div className="nm">{l.name}{" "}<span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>({srcLabel(l.source)})</span>{l.is_test && <span className="bucket-tag" style={{ marginLeft: 6 }}>TEST</span>}</div>
                        <LeadPhone phone={l.phone} missCount={l.miss_count} />
                      </div>
                    </div>
                  </td>
                  <td><CallConnected leadId={l.id} lastNoAt={l.last_no_timestamp} /></td>
                  <td><DueChip at={l.follow_up_at} /></td>
                  <td>
                    {l.miss_count > 0
                      ? <span className={"miss-chip" + (l.miss_count >= 5 ? " hot" : "")}>{l.miss_count} miss</span>
                      : <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>}
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
      </div>
    </>
  );
}
