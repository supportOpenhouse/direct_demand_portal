/* Every lead in one table, with the stage ramp as large clickable count boxes.

   The per-stage pages are each a plain equality on `leads.stage`, so a lead lives on
   exactly one of them and there has never been a single place to see the whole book.
   This is that place — read-only triage, not a replacement for the worklists. */
import { useMemo, useState } from "react";
import { formatDateTime, useAllLeads, useAllSocieties, useAssignees } from "../lib/queries";
import { LEAD_SEGMENTS, isNewToday, leadMatchesQuery, newFirst, segHue, sourcesLabel, stageLabel } from "../lib/leads";
import { matchesOption, rmOptions } from "../components/Filters";
import { EXTRA_DEFAULTS, extraFields, passExtras, sourceMatches, sourceOptions } from "../lib/leadFilters";
import { useFilterValues } from "../components/FilterBar";
import { LeadToolbar, cityMatches } from "../components/LeadToolbar";
import { Skeleton, SkeletonTable } from "../components/Skeleton";
import { useSort, SortTh } from "../lib/useSort";
import { CallButton } from "../components/CallButton";
import LeadPhone from "../components/LeadPhone";
import { ExportCsvButton } from "../components/ExportCsvButton";
import type { Lead } from "../lib/api";
import { useRowOpen } from "../components/LeadModal";
import { TopbarSlot } from "../components/TopbarSlot";
import { Pager, usePaging } from "../components/Pager";
import { StageChip } from "../components/StageChip";
import { ArrivalCount, NewBadge, SourceChips } from "../components/StageChip";


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

  const { sorted: sortedRows, sortKey, dir, onSort } = useSort(filtered, {
    name: (l) => l.name,
    phone: (l) => l.phone,
    source: (l) => sourcesLabel(l),
    stage: (l) => stageLabel(l.stage),
    city: (l) => l.city,
    society: (l) => l.society,
    assigned: (l) => l.assigned_to,
    created: (l) => (l.received_at ? Date.parse(l.received_at) : null),
    activity: (l) => (l.latest_activity_at ? Date.parse(l.latest_activity_at) : null),
  });

  // NEW-badge leads on top, the chosen sort within each group
  const list = newFirst(sortedRows);

  const totalPassing = all.filter((l) => pass(l, "seg")).length;
  /* 4,000 rows in one DOM table is a scroll nobody finishes and a slow first
     paint. Paged in the client — the data is already here, only the slice moves. */
  // every assignable RM, so the filter can ask about one with no rows here
  const assignees = useAssignees();
  const societies = useAllSocieties();
  const pg = usePaging(list);

  return (
    <>
      {/* Page actions live in the topbar strip, not in the toolbar. */}
      <TopbarSlot><ExportCsvButton leads={list} name="all-leads" /></TopbarSlot>

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
      {!isLoading && <Pager page={pg.page} pages={pg.pages} size={pg.size} total={list.length} onPage={pg.setPage} />}

      <div className="card">
        <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <SortTh label="Lead" sortKey="name" activeKey={sortKey} dir={dir} onSort={onSort} style={{ width: 230 }} />
              <SortTh label="Phone" sortKey="phone" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Source" sortKey="source" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Stage" sortKey="stage" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="City" sortKey="city" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Society" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Assigned To" sortKey="assigned" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Received" sortKey="created" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Latest activity" sortKey="activity" activeKey={sortKey} dir={dir} onSort={onSort} />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <SkeletonTable rows={10} cols={9} />
            ) : list.length === 0 ? (
              <tr><td colSpan={9}><div className="empty" style={{ padding: 30 }}>
                {all.length === 0 ? "No leads yet." : "No leads match the filters."}
              </div></td></tr>
            ) : (
              pg.slice.map((l) => (
                <tr key={l.id} {...rowOpen(l.id)}>
                  <td className="lead-cell" title={l.name ?? ""}>
                                            <div className="nm">
                          {isNewToday(l) && <NewBadge size={18} style={{ marginRight: 6 }} />}
                          {l.name}<ArrivalCount lead={l} />
                        </div>
                  </td>
                  <td className="ph-cell" onClick={(e) => e.stopPropagation()}>
                    <div className="phone-cell">
                      <CallButton leadId={l.id} disabled={!l.phone} />
                      <LeadPhone phone={l.phone} missCount={l.miss_count} />
                    </div>
                  </td>
                  <td className="cell-tight"><SourceChips lead={l} /></td>
                  <td className="cell-tight"><StageChip stage={l.stage} /></td>
                  <td className="cell-tight">{l.city || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                  <td className="cell-text" title={l.society || ""}><span>{l.society || "—"}</span></td>
                  <td>{l.assigned_to || <span style={{ color: "var(--muted)" }}>Unassigned</span>}</td>
                  <td style={{ whiteSpace: "nowrap", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                    {l.received_at ? new Date(l.received_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) : "—"}
                  </td>
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
