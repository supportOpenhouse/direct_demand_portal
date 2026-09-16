/* The callback worklist, used by two pages:

     Follow Up          (stage='follow_up')        — we've spoken to them, callback due
     Call Not Received  (stage='call_not_received') — called, never yet reached

   Same columns and same actions, so it's one component with a segment prop rather
   than two near-identical files. Rows are gated: Yes logs a connected call and opens
   the lead, No asks why and reschedules accordingly (10 misses on a never-reached
   lead → RNR; an invalid number → Rejected). */
import { useState } from "react";
import { formatDateTime, useAllSocieties, useAssignees, useLeads } from "../lib/queries";
import { Lead } from "../lib/api";
import { isNewToday, leadMatchesQuery, newFirst, sourcesLabel } from "../lib/leads";
import { ArrivalCount, SourceChips } from "../components/StageChip";
import { sourceMatches, sourceOptions } from "../lib/leadFilters";
import { DATE_PRESETS, rmOptions } from "../components/Filters";
import { countedOptions, matchesOption, inDatePreset, type DatePreset } from "../components/Filters";
import { EXTRA_DEFAULTS, extraFields, passExtras } from "../lib/leadFilters";
import { useSort, SortTh } from "../lib/useSort";
import { ExportCsvButton } from "../components/ExportCsvButton";
import { useRowSelection } from "../lib/useRowSelection";
import { BulkAssignBar } from "../components/BulkAssignBar";
import { NotesCell } from "../components/NotesCell";
import { AssignControl } from "../components/AssignControl";
import { CallButton } from "../components/CallButton";
import LeadPhone from "../components/LeadPhone";
import { SkeletonTable } from "../components/Skeleton";
import { useFilterValues } from "../components/FilterBar";
import { LeadToolbar, cityMatches } from "../components/LeadToolbar";
import { TopbarSlot } from "../components/TopbarSlot";
import { SelectFirst } from "../components/SelectFirst";
import { IconClock } from "../components/icons";
import { Pager, usePaging } from "../components/Pager";
import { useRowOpen } from "../components/LeadModal";
import { NewBadge } from "../components/StageChip";

// follow-up due → friendly label + overdue/soon class
function DueChip({ at }: { at: string | null }) {
  if (!at) return <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>;
  const mins = Math.round((new Date(at).getTime() - Date.now()) / 60000);
  const label = new Date(at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  let cls = "", suffix = "";
  if (mins < 0) { cls = " overdue"; suffix = ` · ${Math.abs(mins) >= 60 ? Math.round(Math.abs(mins) / 60) + "h" : Math.abs(mins) + "m"} late`; }
  else if (mins < 60) { cls = " soon"; suffix = ` · in ${mins}m`; }
  return <span className={`fu-chip${cls}`}><IconClock /> {label}{suffix}</span>;
}

// same calendar day as now (local)
const isToday = (iso: string | null): boolean => {
  if (!iso) return false;
  const d = new Date(iso), n = new Date();
  return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate();
};

export default function Followup({ segment = "followup" }: { segment?: string } = {}) {
  const { data, isLoading } = useLeads(segment);
  // Page-local search and city tab. Local on purpose: a query that outlives the
  // page it was typed on is what the global box got wrong.
  const [q, setQ] = useState("");
  const [cityTab, setCityTab] = useState("");
  const [selectMode, setSelectMode] = useState(false);
  const { values: f, set, clear } = useFilterValues({
    source: "", owner: "", datePreset: "" as DatePreset, dateFrom: "", dateTo: "",
    ...EXTRA_DEFAULTS,
  });
  const { source, owner, datePreset, dateFrom, dateTo } = f;
  const societies = useAllSocieties();

  const all = data?.items ?? [];
  // faceted counts: each dropdown counts leads passing all the OTHER filters (skip its own)
  const pass = (l: Lead, skip?: string) =>
    (skip === "source" || sourceMatches(l, source)) &&
    (skip === "city" || cityMatches(l.city, cityTab)) &&
    (skip === "owner" || matchesOption(l.assigned_to, owner)) &&
    inDatePreset(l.follow_up_at, datePreset, dateFrom, dateTo) &&
    passExtras(l, f, skip) &&
    leadMatchesQuery(q, l);
  const filtered = all.filter((l) => pass(l));
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
  const { sorted: sortedRows, sortKey, dir, onSort } = useSort<Lead>(ordered, {
    name: (l) => l.name,
    phone: (l) => l.phone,
    source: (l) => sourcesLabel(l),
    due: (l) => (l.follow_up_at ? Date.parse(l.follow_up_at) : null),
    misses: (l) => l.miss_count,
    assigned: (l) => l.assigned_to,
    society: (l) => l.society,
    activity: (l) => (l.latest_activity_at ? Date.parse(l.latest_activity_at) : null),
  });
  // NEW-badge leads on top; the callback ranking above still orders each group
  const list = newFirst(sortedRows);
  const rowOpen = useRowOpen();
  // every assignable RM, so the filter can ask about one with no rows here
  const assignees = useAssignees();
  const pg = usePaging(list);
  const sel = useRowSelection(list.map((l) => l.id));

  return (
    <>
      {/* Page actions belong in the topbar strip, not repeated in the toolbar. */}
      <TopbarSlot>
        <button className={"btn sm" + (selectMode ? "" : " ghost")} onClick={() => setSelectMode((v) => !v)}>
          {selectMode ? "Exit Select" : "Select"}
        </button>
        {selectMode && <SelectFirst total={sel.visibleCount} onPick={sel.selectFirst} btnClass="btn ghost sm" />}
        <ExportCsvButton leads={list} name="follow-up" />
      </TopbarSlot>
      <div className="section-head">
        <div>
          <div style={{ display: "flex", gap: 14, alignItems: "center", fontSize: 11.5, color: "var(--muted)" }}>
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 22, height: 12, borderRadius: 3, background: "var(--emerald-soft)", border: "1px solid var(--emerald-soft-2)" }} /> moved here today
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 22, height: 12, borderRadius: 3, background: "var(--blue-soft)", border: "1px solid var(--blue-soft-2)" }} /> follow-up due today
            </span>
          </div>
        </div>
        </div>

        <LeadToolbar
          city={cityTab} onCity={setCityTab} q={q} onQ={setQ}
          fields={[
            { key: "source", label: "Source",
              options: sourceOptions(all.filter((l) => pass(l, "source")), source) },
            { key: "owner", label: "Assigned RM",
              options: rmOptions(all.filter((l) => pass(l, "owner")), (l) => l.assigned_to,
                                 (assignees.data?.items ?? []).map((a) => a.name), owner) },
            { key: "datePreset", label: "Due", options: DATE_PRESETS,
              format: (v: string) => "Due: " + (DATE_PRESETS.find((d) => d.value === v)?.label ?? v) },
            { key: "dateFrom", label: "Due from", kind: "date", hidden: f.datePreset !== "custom" },
            { key: "dateTo", label: "Due to", kind: "date", hidden: f.datePreset !== "custom" },
            ...extraFields(all, pass, f, societies.data?.items ?? [], { rejected: false }),
          ]}
          values={f} onChange={set} onClear={clear}
        />

      {selectMode && (
        <BulkAssignBar ids={sel.activeIds} onDone={sel.clear}
          total={sel.visibleCount} onSelectFirst={sel.selectFirst} />
      )}

      <Pager page={pg.page} pages={pg.pages} size={pg.size} total={list.length} onPage={pg.setPage} />

      <div className="card">
        <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {selectMode && (
                <th style={{ width: 30 }}>
                  <input type="checkbox" checked={sel.allChecked} onChange={sel.toggleAll} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} title="Select all" />
                </th>
              )}
              <SortTh label="Lead" sortKey="name" activeKey={sortKey} dir={dir} onSort={onSort} style={{ width: 230 }} />
              <SortTh label="Phone" sortKey="phone" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Source" sortKey="source" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Follow-up due" sortKey="due" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Misses" sortKey="misses" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Society" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Assigned To" sortKey="assigned" activeKey={sortKey} dir={dir} onSort={onSort} />
              <th>Notes</th>
              <SortTh label="Latest activity" sortKey="activity" activeKey={sortKey} dir={dir} onSort={onSort} />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <SkeletonTable rows={8} cols={9 + (selectMode ? 1 : 0)} />
            ) : list.length === 0 ? (
              <tr><td colSpan={9 + (selectMode ? 1 : 0)}><div className="empty" style={{ padding: 30 }}>
                {all.length === 0 ? "No callbacks scheduled right now." : "No leads match the search / filters."}
              </div></td></tr>
            ) : (
              pg.slice.map((l) => (
                <tr
                  key={l.id}
                  /* green (arrived in Follow-up today) takes priority over blue (due today) */
                  {...rowOpen(l.id)}
                  className={"lead-row" + (isToday(l.follow_up_since) ? " fu-arrived" : isToday(l.follow_up_at) ? " fu-due" : "")}
                >
                  {selectMode && (
                    <td onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={sel.has(l.id)} onChange={() => sel.toggle(l.id)} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} />
                    </td>
                  )}
                  <td className="lead-cell" title={l.name ?? ""}>
                                            <div className="nm">{isNewToday(l) && <NewBadge size={18} style={{ marginRight: 6 }} />}{l.name}<ArrivalCount lead={l} />{l.is_test && <span className="bucket-tag" style={{ marginLeft: 6 }}>TEST</span>}</div>
                  </td>
                  <td className="ph-cell" onClick={(e) => e.stopPropagation()}>
                    <div className="phone-cell">
                      <CallButton leadId={l.id} disabled={!l.phone} />
                      <LeadPhone phone={l.phone} missCount={l.miss_count} />
                    </div>
                  </td>
                  <td className="cell-tight"><SourceChips lead={l} /></td>
                  <td className="cell-tight"><DueChip at={l.follow_up_at} /></td>
                  <td>
                    {l.miss_count > 0
                      ? <span className={"miss-chip" + (l.miss_count >= 5 ? " hot" : "")}>{l.miss_count} miss</span>
                      : <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>}
                  </td>
                  <td className="cell-text" style={{ fontSize: 12.5, color: "var(--ink-2)" }} title={l.society || ""}><span>{l.society || "—"}</span></td>
                  <td onClick={(e) => e.stopPropagation()}><AssignControl leadId={l.id} assignedTo={l.assigned_to} /></td>
                  <td onClick={(e) => e.stopPropagation()}><NotesCell leadId={l.id} latest={l.latest_note} count={l.note_count} /></td>
                  <td className="cell-tight" style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)" }}>
                    {l.latest_activity_at ? formatDateTime(l.latest_activity_at) : "—"}
                  </td>
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
