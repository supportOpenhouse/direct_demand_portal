/* Qualified / Pipeline / Converted leads — 1:1 with the prototype's tplLeads()
   table (Lead · Source · Stage · TAT · Society · Assigned · Visits). Same component
   for all three segments, switched by the `segment` prop. */
import { useState } from "react";
import { useAllSocieties, useAssignees, useLeads } from "../lib/queries";
import { Lead } from "../lib/api";
import { SEGMENT_STAGES, leadMatchesQuery, newFirst } from "../lib/leads";
import { StageBoxes } from "../components/StageBoxes";
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

const NOUN: Record<string, string> = {
  qualified: "qualified leads", future_prospect: "future prospects", visited: "visited leads",
  converted: "converted leads", rejected: "rejected leads",
};

const TITLE: Record<string, string> = {
  qualified: "Qualified Leads", future_prospect: "Future Prospect", visited: "Visited Leads",
  converted: "Converted Leads", rejected: "Rejected Leads",
};

/** Each segment's original columns, in their original order — what Reset returns to.
    Every page may add any column; these are only the starting point. */
function segmentCols(segment: string): string[] {
  if (segment === "rejected")
    return ["name", "phone", "source", "reason", "rejectNote", "created", "rejectedOn", "notes", "assigned", "activity"];
  /* Stage only on Visited Leads. Everywhere else every row reads the same word, so the
     column is a wall of one value — but Visited holds visit_scheduled AND
     revisit_scheduled, and telling a first visit from a return is the point of the page. */
  const stage = segment === "visited" ? ["stage"] : [];
  // ★ hot marking is for leads that have actually been out on a visit
  const hot = segment === "visited" ? ["hot"] : [];
  return [...hot, "name", "phone", "source", ...stage, "society", "notes", "assigned", "activity", "actions"];
}

export default function LeadsSegment({ segment }: { segment: "qualified" | "future_prospect" | "visited" | "converted" | "rejected" }) {
  const rejected = segment === "rejected";
  // Visited Leads is the only page whose rows carry a booked visit, so it owns the
  // ★ hot column, the visit-status filter and the Stage column.
  const hasVisits = segment === "visited";
  const isPipeline = hasVisits;
  const showStage = hasVisits;
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
  // stage boxes, on the pages that hold more than one stage — own state, not a filter
  // chip, for the same reason as on Call Not Received
  const stages = SEGMENT_STAGES[segment];
  const [stage, setStage] = useState("");
  const [planner, setPlanner] = useState<Lead | null>(null);
  const [managing, setManaging] = useState<Lead | null>(null);

  const all = data?.items ?? [];
  // `pass(l, skip)` applies every filter except `skip`. Each dropdown's counts are
  // computed over the leads passing all the OTHER filters (faceted), so they react to
  // the current selection; `filtered` (skip nothing) drives the table + header count.
  // `skip` takes a list too — the ALL box counts the page with BOTH box selections
  // ignored, otherwise picking "Visit completed" makes ALL read that same number.
  /* VISIT SCHEDULED means the visit is still ahead of them: a lead whose latest visit is
     completed or cancelled is counted by those boxes instead, never twice. The count and
     the box's own filter share this one rule, so clicking a box shows what it counted —
     and the four boxes then sum to ALL. */
  const settled = (l: Lead) => l.visit_status === "completed" || l.visit_status === "cancelled";
  const stageBox = (l: Lead) =>
    hasVisits && l.stage === "visit_scheduled" && settled(l) ? "" : l.stage;
  const pass = (l: Lead, skip?: string | string[]) => {
    const off = (k: string) => skip === k || (Array.isArray(skip) && skip.includes(k));
    return (
      (off("stage") || !stage || stageBox(l) === stage) &&
      (off("source") || sourceMatches(l, source)) &&
      (off("city") || cityMatches(l.city, cityTab)) &&
      (off("owner") || matchesOption(l.assigned_to, owner)) &&
      (!hotOnly || l.is_hot) &&
      (off("visitStatus") || !visitStatus || l.visit_status === visitStatus) &&
      passExtras(l, f, Array.isArray(skip) ? undefined : skip) &&
      leadMatchesQuery(q, l)
    );
  };
  const filtered = all.filter((l) => pass(l));
  /* The boxes are ONE axis — a lead belongs to exactly one of them — so every box is
     counted with BOTH box selections ignored, and the row of numbers doesn't move when
     you pick one. Counting each box within the other's selection is what made them
     rewrite each other on every click. They always sum to ALL. */
  const boxScope = stages ? all.filter((l) => pass(l, ["stage", "visitStatus"])) : [];
  const byStage: Record<string, number> = {};
  for (const l of boxScope) {
    const box = stageBox(l);
    if (box) byStage[box] = (byStage[box] ?? 0) + 1;
  }
  /* Visit completed / cancelled are the VISIT's status, not the lead's stage, but they
     sit in the same row and split the same leads. They SET the page's visit filter, so
     the box and the Filters dropdown stay one value. */
  const visitBoxes = [
    { key: "completed", label: "Visit completed", hue: "var(--emerald)" },
    { key: "cancelled", label: "Visit cancelled", hue: "var(--coral)" },
  ].map((b) => ({ ...b, count: boxScope.filter((l) => l.visit_status === b.key).length }));
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

      {/* one axis, so picking a box clears the other kind — two at once would ask for
          leads that are in both, which by the rule above is nobody */}
      {stages && (
        <StageBoxes stages={stages} counts={byStage} total={boxScope.length}
          value={stage} onChange={(st) => { setStage(st); if (st) set("visitStatus", ""); }}
          loading={isLoading}
          extra={hasVisits ? visitBoxes : []} extraValue={visitStatus}
          onExtra={(k) => { set("visitStatus", k); if (k) setStage(""); }} />
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
