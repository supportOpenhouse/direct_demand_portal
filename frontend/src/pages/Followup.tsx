/* The callback worklist, used by two pages:

     Follow Up          (stage='follow_up')        — we've spoken to them, callback due
     Call Not Received  (stage='call_not_received') — called, never yet reached

   Same columns and same actions, so it's one component with a segment prop rather
   than two near-identical files. Rows are gated: Yes logs a connected call and opens
   the lead, No asks why and reschedules accordingly (10 misses on a never-reached
   lead → RNR; an invalid number → Rejected). */
import { useState } from "react";
import { useAllSocieties, useAssignees, useLeads } from "../lib/queries";
import { Lead } from "../lib/api";
import { SEGMENT_STAGES, leadMatchesQuery, newFirst } from "../lib/leads";
import { StageBoxes } from "../components/StageBoxes";
import { sourceMatches, sourceOptions } from "../lib/leadFilters";
import { DATE_PRESETS, rmOptions } from "../components/Filters";
import { matchesOption, inDatePreset, type DatePreset } from "../components/Filters";
import { EXTRA_DEFAULTS, extraFields, passExtras } from "../lib/leadFilters";
import { useSort } from "../lib/useSort";
import { ExportCsvButton } from "../components/ExportCsvButton";
import { useRowSelection } from "../lib/useRowSelection";
import { BulkAssignBar } from "../components/BulkAssignBar";
import { useFilterValues } from "../components/FilterBar";
import { LeadToolbar, cityMatches } from "../components/LeadToolbar";
import { TopbarSlot } from "../components/TopbarSlot";
import { Pager, usePaging } from "../components/Pager";
import { LeadTable } from "../features/leadTable/LeadTable";
import { LEAD_SORTERS } from "../features/leadTable/columns";
import { useLeadColumns } from "../features/leadTable/ColumnSettings";
import { useRowOpen } from "../components/LeadModal";

// follow-up due → friendly label + overdue/soon class
// same calendar day as now (local)
const isToday = (iso: string | null): boolean => {
  if (!iso) return false;
  const d = new Date(iso), n = new Date();
  return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate();
};

/** This page's original columns, in their original order — what Reset returns to. */
const FOLLOWUP_COLS = ["name", "phone", "source", "due", "misses", "society", "assigned", "notes", "activity"];

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
  /* The stage boxes' selection. Its own state, not a FilterBar value: the boxes ARE the
     control, and as a filter value it would also appear as a removable chip — two controls
     for one choice. Home → Table keeps its segment boxes apart the same way. */
  const stages = SEGMENT_STAGES[segment];
  const [stage, setStage] = useState("");

  const all = data?.items ?? [];
  // faceted counts: each dropdown counts leads passing all the OTHER filters (skip its own)
  const pass = (l: Lead, skip?: string) =>
    (skip === "stage" || !stage || l.stage === stage) &&
    (skip === "source" || sourceMatches(l, source)) &&
    (skip === "city" || cityMatches(l.city, cityTab)) &&
    (skip === "owner" || matchesOption(l.assigned_to, owner)) &&
    inDatePreset(l.follow_up_at, datePreset, dateFrom, dateTo) &&
    passExtras(l, f, skip) &&
    leadMatchesQuery(q, l);
  const filtered = all.filter((l) => pass(l));
  // faceted, like every dropdown here: each box counts leads passing all the OTHER filters
  const inStageScope = stages ? all.filter((l) => pass(l, "stage")) : [];
  const byStage: Record<string, number> = {};
  for (const l of inStageScope) byStage[l.stage] = (byStage[l.stage] ?? 0) + 1;
  /* Most-actionable first. The row tints these used to mirror are gone, but the ORDER
     still earns its keep — it is what puts today's work at the top:
       0 moved into Follow-up today
       1 follow-up due today
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
  const { sorted: sortedRows, sortKey, dir, onSort } = useSort<Lead>(ordered, LEAD_SORTERS);
  // NEW-badge leads on top; the callback ranking above still orders each group
  const list = newFirst(sortedRows);
  const rowOpen = useRowOpen();
  // every assignable RM, so the filter can ask about one with no rows here
  const assignees = useAssignees();
  const pg = usePaging(list);
  const sel = useRowSelection(list.map((l) => l.id));
  /* Own key per page. Both pages render this component, and sharing "follow-up" meant
     arranging columns on Call Not Received silently rearranged Call Back Again. The
     follow-up key is unchanged so nobody's existing Call Back Again layout is lost. */
  const cnr = segment === "call_not_received";
  const columns = useLeadColumns(cnr ? "call-not-received" : "follow-up", FOLLOWUP_COLS,
                                 cnr ? "Call Not Received" : "Call Back Again");

  return (
    <>
      {/* Page actions belong in the topbar strip, not repeated in the toolbar. */}
      <TopbarSlot>
        {columns.button}
        <ExportCsvButton leads={list} name="follow-up" />
      </TopbarSlot>
      {columns.modal}
      <div className="section-head">
        <div>
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

      {stages && (
        <StageBoxes stages={stages} counts={byStage} total={inStageScope.length}
          value={stage} onChange={setStage} loading={isLoading} />
      )}

      {selectMode && (
        <BulkAssignBar ids={sel.activeIds} onDone={sel.clear} total={sel.visibleCount} />
      )}

      <Pager page={pg.page} pages={pg.pages} size={pg.size} total={list.length} onPage={pg.setPage}
        sizeChoice={pg.sizeChoice} onSize={pg.setSize}
        select={{ on: selectMode, onToggle: () => setSelectMode((v) => !v),
                  total: sel.visibleCount, onPick: sel.selectFirst }} />

      <div className="card">
        <div className="table-wrap">
        <LeadTable
          cols={columns.cols} rows={pg.slice}
          sortKey={sortKey} dir={dir} onSort={onSort}
          selectMode={selectMode} sel={sel}
          isLoading={isLoading} rowProps={rowOpen}
          empty={all.length === 0 ? "No callbacks scheduled right now." : "No leads match the search / filters."}
        />
        </div>
      </div>
    </>
  );
}
