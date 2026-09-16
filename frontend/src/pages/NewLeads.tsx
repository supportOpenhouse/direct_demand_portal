/* New Leads — 1:1 with the prototype's tplNewLeads(), wired to GET /v1/leads?segment=new.
   Two source categories (Meta + listing portals) land in one table; rows clickable → lead detail. */
import { useAllSocieties, useAssignees, useLeadCounts, useLeads } from "../lib/queries";
import { Lead } from "../lib/api";
import { leadMatchesQuery, newFirst } from "../lib/leads";
import { sourceMatches, sourceOptions } from "../lib/leadFilters";
import { DATE_PRESETS, rmOptions } from "../components/Filters";
import { uniqueValues, matchesOption, inDatePreset, type DatePreset } from "../components/Filters";
import { EXTRA_DEFAULTS, extraFields, passExtras } from "../lib/leadFilters";
import { useSort } from "../lib/useSort";
import { ExportCsvButton } from "../components/ExportCsvButton";
import { useRowSelection } from "../lib/useRowSelection";
import { BulkAssignBar } from "../components/BulkAssignBar";
import { useState } from "react";
import { useFilterValues } from "../components/FilterBar";
import { LeadToolbar, cityMatches } from "../components/LeadToolbar";
import { TopbarSlot } from "../components/TopbarSlot";
import { Pager, usePaging } from "../components/Pager";
import { LeadTable } from "../features/leadTable/LeadTable";
import { LEAD_SORTERS } from "../features/leadTable/columns";
import { useLeadColumns } from "../features/leadTable/ColumnSettings";
import { useRowOpen } from "../components/LeadModal";

/** This page's original columns, in their original order — what Reset returns to. */
const NEW_LEADS_COLS = ["name", "phone", "source", "city", "society", "budget", "plan", "created", "assigned", "notes", "activity"];

export default function NewLeads() {
  const { data, isLoading } = useLeads("new");
  const { data: counts } = useLeadCounts();
  // Page-local search and city tab. Local on purpose: a query that outlives the
  // page it was typed on is what the global box got wrong.
  const [q, setQ] = useState("");
  const [cityTab, setCityTab] = useState("");
  const [selectMode, setSelectMode] = useState(false);
  const { values: f, set, setValues, clear } = useFilterValues({
    source: "", owner: "", plan: "", datePreset: "" as DatePreset, dateFrom: "", dateTo: "",
    ...EXTRA_DEFAULTS,
  });
  const { source, owner, plan, datePreset, dateFrom, dateTo } = f;
  const societies = useAllSocieties();

  // "Plan to buy" is a Meta-form field — irrelevant for listing sources (99acres / MagicBricks)
  const showPlan = source === "meta";
  // switching away from Meta drops the now-hidden plan filter so it can't silently constrain results
  // switching away from Meta drops the now-hidden plan filter so it can't silently
  // constrain results. One setValues, because both keys change together.
  const onChange = (k: string, v: any) =>
    setValues((p) => (k === "source" && v !== "meta" ? { ...p, source: v, plan: "" } : { ...p, [k]: v }));

  const all = data?.items ?? [];
  // faceted counts: each dropdown counts leads passing all the OTHER filters (skip its own)
  const pass = (l: Lead, skip?: string) =>
    (skip === "source" || sourceMatches(l, source)) &&
    (skip === "city" || cityMatches(l.city, cityTab)) &&
    (!plan || l.plan_to_buy === plan) &&
    (skip === "owner" || matchesOption(l.assigned_to, owner)) &&
    inDatePreset(l.received_at, datePreset, dateFrom, dateTo) &&
    passExtras(l, f, skip) &&
    leadMatchesQuery(q, l);
  const filtered = all.filter((l) => pass(l));
  const { sorted: sortedRows, sortKey, dir, onSort } = useSort<Lead>(filtered, LEAD_SORTERS);
  // NEW-badge leads on top, the chosen sort within each group
  const list = newFirst(sortedRows);
  const rowOpen = useRowOpen();
  // every assignable RM, so the filter can ask about one with no rows here
  const assignees = useAssignees();
  const pg = usePaging(list);
  const sel = useRowSelection(list.map((l) => l.id));
  const columns = useLeadColumns("new-leads", NEW_LEADS_COLS, "New Leads");

  return (
    <>
      {/* Page actions belong in the topbar strip, not repeated in the toolbar. */}
      <TopbarSlot>
        {columns.button}
        <ExportCsvButton leads={list} name="new-leads" />
      </TopbarSlot>
      {columns.modal}
      <div className="section-head" style={{ marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          {data?.status === "ok" && (
            <>
              <span style={{ fontFamily: "var(--font-display)", fontSize: 26, fontWeight: 700, letterSpacing: "-.02em", lineHeight: 1 }}>
                {(list.length !== all.length ? list.length : all.length).toLocaleString("en-IN")}
              </span>
              <span style={{ fontSize: 12.5, color: "var(--muted)", fontWeight: 500 }}>
                {list.length !== all.length ? `of ${all.length.toLocaleString("en-IN")} new` : "new leads"}
                {counts?.status === "ok" && ` · ${counts.total_nontest.toLocaleString("en-IN")} total`}
              </span>
            </>
          )}
        </div>
      </div>

        <LeadToolbar
          city={cityTab} onCity={setCityTab} q={q} onQ={setQ}
          fields={[
            { key: "source", label: "Source",
              options: sourceOptions(all.filter((l) => pass(l, "source")), source) },
            { key: "plan", label: "Plan", options: uniqueValues(all, (l) => l.plan_to_buy), hidden: !showPlan },
            { key: "owner", label: "Assigned RM",
              options: rmOptions(all.filter((l) => pass(l, "owner")), (l) => l.assigned_to,
                                 (assignees.data?.items ?? []).map((a) => a.name), owner) },
            { key: "datePreset", label: "Received", options: DATE_PRESETS,
              format: (v: string) => "Received: " + (DATE_PRESETS.find((d) => d.value === v)?.label ?? v) },
            { key: "dateFrom", label: "Received from", kind: "date", hidden: f.datePreset !== "custom" },
            { key: "dateTo", label: "Received to", kind: "date", hidden: f.datePreset !== "custom" },
            ...extraFields(all, pass, f, societies.data?.items ?? [], { rejected: false }),
          ]}
          values={f} onChange={onChange} onClear={clear}
        />

      {selectMode && (
        <BulkAssignBar ids={sel.activeIds} onDone={sel.clear} total={sel.visibleCount} />
      )}

      <Pager page={pg.page} pages={pg.pages} size={pg.size} total={list.length} onPage={pg.setPage}
        sizeChoice={pg.sizeChoice} onSize={pg.setSize}
        select={{ on: selectMode, onToggle: () => setSelectMode((v) => !v),
                  total: sel.visibleCount, onPick: sel.selectFirst }} />

      <div className="card panel-pad" id="needing-action">
        <div className="table-wrap">
        <LeadTable
          cols={columns.cols} rows={pg.slice}
          sortKey={sortKey} dir={dir} onSort={onSort}
          selectMode={selectMode} sel={sel}
          isLoading={isLoading} rowProps={rowOpen}
          empty={all.length === 0 ? "No new leads right now." : "No leads match the search / filters."}
        />
        </div>
      </div>
    </>
  );
}
