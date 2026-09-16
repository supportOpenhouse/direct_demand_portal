/* Qualified / Pipeline / Converted leads — 1:1 with the prototype's tplLeads()
   table (Lead · Source · Stage · TAT · Society · Assigned · Visits). Same component
   for all three segments, switched by the `segment` prop. */
import { useState } from "react";
import { useAllSocieties, useAssignees, useLeads } from "../lib/queries";
import { Lead } from "../lib/api";
import { leadMatchesQuery, newFirst } from "../lib/leads";
import { sourceMatches, sourceOptions } from "../lib/leadFilters";
import { matchesOption, rmOptions } from "../components/Filters";
import { EXTRA_DEFAULTS, extraFields, passExtras } from "../lib/leadFilters";
import { useSort } from "../lib/useSort";
import { ExportCsvButton } from "../components/ExportCsvButton";
import { useRowSelection } from "../lib/useRowSelection";
import { BulkAssignBar } from "../components/BulkAssignBar";
import { VisitPlanner } from "../features/VisitPlanner";
import ManageVisitsModal from "../features/ManageVisitsModal";
import { useFilterValues } from "../components/FilterBar";
import { LeadToolbar, cityMatches } from "../components/LeadToolbar";
import { useRowOpen } from "../components/LeadModal";
import { TopbarSlot } from "../components/TopbarSlot";
import { Pager, usePaging } from "../components/Pager";
import { LeadTable } from "../features/leadTable/LeadTable";
import { LEAD_SORTERS } from "../features/leadTable/columns";
import { useLeadColumns } from "../features/leadTable/ColumnSettings";

const NOUN: Record<string, string> = { qualified: "qualified leads", pipeline: "visited leads", revisit: "pipeline leads", converted: "converted leads", rejected: "rejected leads" };

const TITLE: Record<string, string> = {
  qualified: "Qualified Leads", pipeline: "Visited Leads", revisit: "Pipeline Leads",
  converted: "Converted Leads", rejected: "Rejected Leads",
};

/** Each segment's original columns, in their original order — what Reset returns to.
    Every page may add any column; these are only the starting point. */
function segmentCols(segment: string): string[] {
  if (segment === "rejected")
    return ["name", "phone", "source", "reason", "rejectNote", "created", "rejectedOn", "notes", "assigned", "activity"];
  // Qualified & Converted had no Stage column — every row would read the same
  const stage = segment === "pipeline" || segment === "revisit" ? ["stage"] : [];
  // ★ hot marking is a Pipeline Leads tool
  const hot = segment === "revisit" ? ["hot"] : [];
  return [...hot, "name", "phone", "source", ...stage, "society", "notes", "assigned", "activity", "actions"];
}

export default function LeadsSegment({ segment }: { segment: "qualified" | "pipeline" | "revisit" | "converted" | "rejected" }) {
  const rejected = segment === "rejected";
  // "pipeline" = Visited Leads (visit booked); "revisit" = Pipeline Leads (revisit booked).
  // Both carry visits, so both get the ★ hot column + visit-status filter.
  const hasVisits = segment === "pipeline" || segment === "revisit";
  const isPipeline = segment === "revisit"; // the Pipeline Leads tab — the only one with ★ hot marking
  // Qualified & Converted drop the Stage column — every row would read the same ("Qualified"/"Won")
  const showStage = !rejected && segment !== "qualified" && segment !== "converted";
  /* One control, one name, everywhere. "Book Revisit" claimed the button could only do
     that, and there was no way to see or change what was already booked — the popup it
     opens now owns new visit / reschedule / revisit / cancel. */
  const { data, isLoading } = useLeads(segment);
  const rowOpen = useRowOpen();
  // Page-local search and city tab. Local on purpose: a query that outlives the
  // page it was typed on is what the global box got wrong.
  const [q, setQ] = useState("");
  const [cityTab, setCityTab] = useState("");
  // Checkboxes appear only in Select mode, matching Direct Inventory's board.
  const [selectMode, setSelectMode] = useState(false);
  // One object, so the chips and the modal read the same state the table filters on.
  const { values: f, set, clear } = useFilterValues({
    source: "", owner: "", visitStatus: "", hotOnly: false,
    ...EXTRA_DEFAULTS,
  });
  const { source, owner, visitStatus, hotOnly } = f;
  const societies = useAllSocieties();
  const [planner, setPlanner] = useState<Lead | null>(null);
  const [managing, setManaging] = useState<Lead | null>(null);

  const all = data?.items ?? [];
  // `pass(l, skip)` applies every filter except `skip`. Each dropdown's counts are
  // computed over the leads passing all the OTHER filters (faceted), so they react to
  // the current selection; `filtered` (skip nothing) drives the table + header count.
  const pass = (l: Lead, skip?: string) =>
    (skip === "source" || sourceMatches(l, source)) &&
    (skip === "city" || cityMatches(l.city, cityTab)) &&
    (skip === "owner" || matchesOption(l.assigned_to, owner)) &&
    (!hotOnly || l.is_hot) &&
    (!visitStatus || l.visit_status === visitStatus) &&
    passExtras(l, f, skip) &&
    leadMatchesQuery(q, l);
  const filtered = all.filter((l) => pass(l));
  const { sorted: sortedRows, sortKey, dir, onSort } = useSort<Lead>(filtered, LEAD_SORTERS);
  // NEW-badge leads on top, the chosen sort within each group
  const list = newFirst(sortedRows);
  // every assignable RM, so the filter can ask about one with no rows here
  const assignees = useAssignees();
  const pg = usePaging(list);
  const sel = useRowSelection(list.map((l) => l.id));
  const columns = useLeadColumns(`segment-${segment}`, segmentCols(segment), TITLE[segment]);

  return (
    <>
      {/* Page actions belong in the topbar strip, not repeated in the toolbar. */}
      <TopbarSlot>
        {columns.button}
        <ExportCsvButton leads={list} name={segment} />
      </TopbarSlot>
      {columns.modal}
      <LeadToolbar
        city={cityTab} onCity={setCityTab} q={q} onQ={setQ}
        fields={[
          { key: "source", label: "Source",
            options: sourceOptions(all.filter((l) => pass(l, "source")), source) },
          { key: "owner", label: "Assigned RM",
            options: rmOptions(all.filter((l) => pass(l, "owner")), (l) => l.assigned_to,
                               (assignees.data?.items ?? []).map((a) => a.name), owner) },
          { key: "visitStatus", label: "Visit", options: ["upcoming", "completed", "cancelled"], hidden: !hasVisits },
          { key: "hotOnly", label: "Hot only", kind: "toggle", hidden: !isPipeline },
          // reject reason / rejected-on only mean anything on the Rejected page
          ...extraFields(all, pass, f, societies.data?.items ?? [], { rejected }),
        ]}
        values={f} onChange={set} onClear={clear}
      />

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
          ctx={{ stageWithVisit: true, onManageVisits: rejected ? undefined : setManaging }}
          sortKey={sortKey} dir={dir} onSort={onSort}
          selectMode={selectMode} sel={sel}
          isLoading={isLoading} rowProps={rowOpen}
          empty={all.length === 0 ? `No ${NOUN[segment]} yet.` : "No leads match the search / filters."}
        />
        </div>
      </div>
      {managing && (
        <ManageVisitsModal
          leadId={managing.id}
          leadName={managing.name}
          /* "+ New visit" books a DIFFERENT property, which is the planner's job —
             hand off to it and close this, rather than rebuild unit picking here. */
          onNewVisit={() => { setPlanner(managing); setManaging(null); }}
          onClose={() => setManaging(null)}
        />
      )}
      {planner && (
        <VisitPlanner leadId={planner.id} leadName={planner.name} leadCity={planner.city} leadPhone={planner.phone} onClose={() => setPlanner(null)} />
      )}
    </>
  );
}
