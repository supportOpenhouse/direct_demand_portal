/* Every lead in one table, with the stage ramp as large clickable count boxes.

   The per-stage pages are each a plain equality on `leads.stage`, so a lead lives on
   exactly one of them and there has never been a single place to see the whole book.
   This is that place — read-only triage, not a replacement for the worklists. */
import { useMemo, useState } from "react";
import { useAllLeads, useAllSocieties, useAssignees } from "../lib/queries";
import { LEAD_SEGMENTS, leadMatchesQuery, newFirst, segHue } from "../lib/leads";
import { matchesOption, rmOptions } from "../components/Filters";
import { EXTRA_DEFAULTS, extraFields, passExtras, sourceMatches, sourceOptions } from "../lib/leadFilters";
import { useFilterValues } from "../components/FilterBar";
import { LeadToolbar, cityMatches } from "../components/LeadToolbar";
import { Skeleton } from "../components/Skeleton";
import { useSort } from "../lib/useSort";
import { ExportCsvButton } from "../components/ExportCsvButton";
import type { Lead } from "../lib/api";
import { useRowOpen } from "../components/LeadModal";
import { TopbarSlot } from "../components/TopbarSlot";
import { Pager, usePaging } from "../components/Pager";
import { LeadTable } from "../features/leadTable/LeadTable";
import { LEAD_SORTERS } from "../features/leadTable/columns";
import { useLeadColumns } from "../features/leadTable/ColumnSettings";


/** This page's original columns, in their original order — what Reset returns to. */
const ALL_LEADS_COLS = ["name", "phone", "source", "stage", "city", "society", "assigned", "created", "activity"];

export default function AllLeads({ toolbarEnd }: { toolbarEnd?: React.ReactNode }) {
  const { leads, isLoading } = useAllLeads(true);
  const rowOpen = useRowOpen();
  // Page-local search and city tab. Local on purpose: a query that outlives the
  // page it was typed on is what the global box got wrong.
  const [q, setQ] = useState("");
  const [cityTab, setCityTab] = useState("");
  const [selectMode, setSelectMode] = useState(false);

  const { values: f, set, clear } = useFilterValues({ source: "", owner: "", ...EXTRA_DEFAULTS });
  // Stage boxes are their own control, not a FilterBar field — they ARE the primary
  // navigation of this view, and burying them in a modal would defeat the point.
  const { values: g, set: setSeg } = useFilterValues({ seg: "" });

  const all = useMemo(() => leads.map((x) => ({ ...x.lead, _seg: x.segment.seg })), [leads]);

  const pass = (l: Lead & { _seg: string }, skip?: string) =>
    (skip === "seg" || !g.seg || l._seg === g.seg) &&
    (skip === "source" || sourceMatches(l, f.source)) &&
    (skip === "city" || cityMatches(l.city, cityTab)) &&
    (skip === "owner" || matchesOption(l.assigned_to, f.owner)) &&
    passExtras(l, f, skip) &&
    leadMatchesQuery(q, l);

  const filtered = all.filter((l) => pass(l));
  // Box counts respect every filter EXCEPT the stage selection — otherwise picking a
  // stage would zero every other box and the ramp would stop being readable.
  const bySeg = useMemo(() => {
    const m: Record<string, number> = {};
    for (const l of all.filter((l) => pass(l, "seg"))) m[l._seg] = (m[l._seg] ?? 0) + 1;
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, f, q, cityTab]);

  const { sorted: sortedRows, sortKey, dir, onSort } = useSort(filtered, LEAD_SORTERS);

  // NEW-badge leads on top, the chosen sort within each group
  const list = newFirst(sortedRows);

  const totalPassing = all.filter((l) => pass(l, "seg")).length;
  /* 4,000 rows in one DOM table is a scroll nobody finishes and a slow first
     paint. Paged in the client — the data is already here, only the slice moves. */
  // every assignable RM, so the filter can ask about one with no rows here
  const assignees = useAssignees();
  const societies = useAllSocieties();
  const pg = usePaging(list);
  const columns = useLeadColumns("all-leads", ALL_LEADS_COLS, "All Leads");

  return (
    <>
      {/* Page actions live in the topbar strip, not in the toolbar. */}
      <TopbarSlot>{columns.button}<ExportCsvButton leads={list} name="all-leads" /></TopbarSlot>
      {columns.modal}

      <LeadToolbar
        city={cityTab} onCity={setCityTab} q={q} onQ={setQ}
        fields={[
          { key: "source", label: "Source",
            options: sourceOptions(all.filter((l) => pass(l, "source")), f.source) },
          { key: "owner", label: "Assigned RM",
            options: rmOptions(all.filter((l) => pass(l, "owner")), (l) => l.assigned_to,
                               (assignees.data?.items ?? []).map((a) => a.name), f.owner) },
          // Home holds every lead, rejected ones included, so it shows the reject filters too
          ...extraFields(all, pass, f, societies.data?.items ?? [], { rejected: true }),
        ]}
        values={f} onChange={set} onClear={clear}
      >
        {toolbarEnd}
      </LeadToolbar>

      <div className="stage-counts">
        <div className="stage-pills">
          <button className={"count-pill" + (g.seg ? "" : " on")} onClick={() => setSeg("seg", "")}>
            {/* Placeholders until ALL eight segment queries have landed. The book is
                eight parallel requests (useAllLeads), and summing whatever has arrived
                made every box visibly count up to its final value as each one landed. */}
            <span className="num">{isLoading ? <Skeleton w={64} h={26} r={6} /> : totalPassing.toLocaleString("en-IN")}</span>
            <span className="lbl">ALL</span>
          </button>
          {LEAD_SEGMENTS.map((s) => {
            return (
              <button key={s.seg}
                className={"count-pill" + (g.seg === s.seg ? " on" : "")}
                style={{ ["--pill-hue" as string]: segHue(s.seg) }}
                onClick={() => setSeg("seg", g.seg === s.seg ? "" : s.seg)}
                title={`Show only ${s.label}`}
              >
                <span className="num">{isLoading ? <Skeleton w={44} h={26} r={6} /> : (bySeg[s.seg] ?? 0).toLocaleString("en-IN")}</span>
                <span className="lbl">{s.label.toUpperCase()}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Same reason as the boxes: "of N" climbed while segments were still arriving. */}
      {!isLoading && <Pager page={pg.page} pages={pg.pages} size={pg.size} total={list.length} onPage={pg.setPage}
        sizeChoice={pg.sizeChoice} onSize={pg.setSize} />}

      <div className="card">
        <div className="table-wrap">
        <LeadTable
          cols={columns.cols} rows={pg.slice} ctx={{ assignReadOnly: true }}
          sortKey={sortKey} dir={dir} onSort={onSort}
          isLoading={isLoading} skeletonRows={10} rowProps={rowOpen}
          empty={all.length === 0 ? "No leads yet." : "No leads match the filters."}
        />
        </div>
      </div>
    </>
  );
}
