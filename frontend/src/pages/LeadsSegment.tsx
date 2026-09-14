/* Qualified / Pipeline / Converted leads — 1:1 with the prototype's tplLeads()
   table (Lead · Source · Stage · TAT · Society · Assigned · Visits). Same component
   for all three segments, switched by the `segment` prop. */
import { useState } from "react";
import { formatDate, useAllSocieties, useAssignees, useLeads, useMarkHot } from "../lib/queries";
import { Lead } from "../lib/api";
import { isNewToday, leadMatchesQuery, srcClass, srcLabel, stageLabel } from "../lib/leads";
import { countedOptions, matchesOption, rmOptions } from "../components/Filters";
import { EXTRA_DEFAULTS, extraFields, passExtras } from "../lib/leadFilters";
import { useSort, SortTh } from "../lib/useSort";
import { ExportCsvButton } from "../components/ExportCsvButton";
import { useRowSelection } from "../lib/useRowSelection";
import { BulkAssignBar } from "../components/BulkAssignBar";
import { NotesCell } from "../components/NotesCell";
import { VisitsCell } from "../components/VisitsCell";
import { AssignControl } from "../components/AssignControl";
import { CallButton } from "../components/CallButton";
import LeadPhone from "../components/LeadPhone";
import { VisitPlanner } from "../features/VisitPlanner";
import { SkeletonTable } from "../components/Skeleton";
import { IconCalendar, IconStar , IconClock} from "../components/icons";
import { useFilterValues } from "../components/FilterBar";
import { LeadToolbar, cityMatches } from "../components/LeadToolbar";
import { useRowOpen } from "../components/LeadModal";
import { TopbarSlot } from "../components/TopbarSlot";
import { SelectFirst } from "../components/SelectFirst";
import { Pager, usePaging } from "../components/Pager";
import { StageChip } from "../components/StageChip";
import { NewBadge } from "../components/StageChip";

const NOUN: Record<string, string> = { qualified: "qualified leads", pipeline: "visited leads", revisit: "pipeline leads", converted: "converted leads", rejected: "rejected leads" };

// ★ toggle — marks a lead hot (Pipeline filter uses it)
function HotStar({ lead }: { lead: Lead }) {
  const mark = useMarkHot();
  return (
    <button
      className={"hot-star" + (lead.is_hot ? " on" : "")}
      title={lead.is_hot ? "Unmark as hot" : "Mark as hot"}
      disabled={mark.isPending}
      onClick={(e) => { e.stopPropagation(); mark.mutate({ id: lead.id, hot: !lead.is_hot }); }}
    >
      <span style={{ opacity: lead.is_hot ? 1 : 0.3 }}><IconStar /></span>
    </button>
  );
}

/* Callback due on a lead that isn't in the callback worklist. Only overdue/today are
   worth flagging — a callback next week is noise on this page. */
function DueBadge({ at }: { at: string | null }) {
  if (!at) return null;
  const mins = Math.round((new Date(at).getTime() - Date.now()) / 60000);
  if (mins > 1440) return null;
  return (
    <span className={"fu-chip" + (mins < 0 ? " overdue" : " soon")} style={{ marginLeft: 6 }}>
      <IconClock /> {mins < 0 ? "callback overdue" : "callback due"}
    </span>
  );
}

export default function LeadsSegment({ segment }: { segment: "qualified" | "pipeline" | "revisit" | "converted" | "rejected" }) {
  const rejected = segment === "rejected";
  // "pipeline" = Visited Leads (visit booked); "revisit" = Pipeline Leads (revisit booked).
  // Both carry visits, so both get the ★ hot column + visit-status filter.
  const hasVisits = segment === "pipeline" || segment === "revisit";
  const isPipeline = segment === "revisit"; // the Pipeline Leads tab — the only one with ★ hot marking
  // Qualified & Converted drop the Stage column — every row would read the same ("Qualified"/"Won")
  const showStage = !rejected && segment !== "qualified" && segment !== "converted";
  const bookLabel = segment === "qualified" ? "Book Visit" : hasVisits ? "Book Revisit" : "Visits";
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

  const all = data?.items ?? [];
  // `pass(l, skip)` applies every filter except `skip`. Each dropdown's counts are
  // computed over the leads passing all the OTHER filters (faceted), so they react to
  // the current selection; `filtered` (skip nothing) drives the table + header count.
  const pass = (l: Lead, skip?: string) =>
    (skip === "source" || !source || l.source === source) &&
    (skip === "city" || cityMatches(l.city, cityTab)) &&
    (skip === "owner" || matchesOption(l.assigned_to, owner)) &&
    (!hotOnly || l.is_hot) &&
    (!visitStatus || l.visit_status === visitStatus) &&
    passExtras(l, f, skip) &&
    leadMatchesQuery(q, l);
  const filtered = all.filter((l) => pass(l));
  const { sorted: list, sortKey, dir, onSort } = useSort<Lead>(filtered, {
    name: (l) => l.name,
    phone: (l) => l.phone,
    source: (l) => srcLabel(l.source),
    stage: (l) => stageLabel(l.stage),
    society: (l) => l.society,
    assigned: (l) => l.assigned_to,
    reason: (l) => l.reject_reason,
    rejected: (l) => (l.rejected_at ? Date.parse(l.rejected_at) : null),
    created: (l) => (l.received_at ? Date.parse(l.received_at) : null),
    notes: (l) => (l.latest_note_at ? Date.parse(l.latest_note_at) : null),
    visit: (l) => l.visit_status,
  });
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
        <ExportCsvButton leads={list} name={segment} />
      </TopbarSlot>
      <LeadToolbar
        city={cityTab} onCity={setCityTab} q={q} onQ={setQ}
        fields={[
          { key: "source", label: "Source",
            options: countedOptions(all.filter((l) => pass(l, "source")), (l) => l.source, "Unknown", srcLabel, source) },
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
              {isPipeline && <th style={{ width: 34 }} title="Hot"><IconStar /></th>}
              <SortTh label="Lead" sortKey="name" activeKey={sortKey} dir={dir} onSort={onSort} style={{ width: 230 }} />
              <SortTh label="Phone" sortKey="phone" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Source" sortKey="source" activeKey={sortKey} dir={dir} onSort={onSort} />
              {rejected ? (
                <>
                  <SortTh label="Reason" sortKey="reason" activeKey={sortKey} dir={dir} onSort={onSort} />
                  <th>Reject note</th>
                  <SortTh label="Created On" sortKey="created" activeKey={sortKey} dir={dir} onSort={onSort} />
                  <SortTh label="Rejected On" sortKey="rejected" activeKey={sortKey} dir={dir} onSort={onSort} />
                </>
              ) : (
                <>
                  {showStage && <SortTh label="Stage" sortKey="stage" activeKey={sortKey} dir={dir} onSort={onSort} />}
                  <SortTh label="Society" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
                </>
              )}
              <SortTh label="Notes" sortKey="notes" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Assigned To" sortKey="assigned" activeKey={sortKey} dir={dir} onSort={onSort} />
              <th></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <SkeletonTable rows={8} cols={6 + (selectMode ? 1 : 0) + (isPipeline ? 1 : 0) + (rejected ? 4 : showStage ? 2 : 1)} />
            ) : list.length === 0 ? (
              <tr><td colSpan={6 + (selectMode ? 1 : 0) + (isPipeline ? 1 : 0) + (rejected ? 4 : showStage ? 2 : 1)}><div className="empty" style={{ padding: 30 }}>
                {all.length === 0 ? `No ${NOUN[segment]} yet.` : "No leads match the search / filters."}
              </div></td></tr>
            ) : (
              pg.slice.map((l) => (
                <tr key={l.id} {...rowOpen(l.id)}>
                  {selectMode && (
                    <td onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={sel.has(l.id)} onChange={() => sel.toggle(l.id)} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} />
                    </td>
                  )}
                  {isPipeline && <td onClick={(e) => e.stopPropagation()}><HotStar lead={l} /></td>}
                  <td className="lead-cell" title={l.name ?? ""}>
                                            <div className="nm">
                          {isNewToday(l) && <NewBadge size={18} style={{ marginRight: 6 }} />}
                          {l.name}
                          {l.is_test && <span className="bucket-tag" style={{ marginLeft: 6 }}>TEST</span>}
                          {/* RNR and Future Prospect keep their own stage but share the
                              Rejected page — the badge is the only thing that tells a
                              parked buyer apart from a dead one in this list */}
                          {rejected && l.stage === "rnr" && (
                            <span className="bucket-tag" style={{ marginLeft: 6 }}>RNR</span>
                          )}
                          {rejected && l.stage === "future_prospect" && (
                            <span className="bucket-tag" style={{ marginLeft: 6 }}>FUTURE PROSPECT</span>
                          )}
                          {/* qualified leads no longer also sit in Follow-up, so the
                              due callback has to be visible here or it's invisible */}
                          {segment === "qualified" && <DueBadge at={l.follow_up_at} />}
                        </div>
                  </td>
                  <td className="ph-cell" onClick={(e) => e.stopPropagation()}>
                    <div className="phone-cell">
                      <CallButton leadId={l.id} disabled={!l.phone} />
                      <LeadPhone phone={l.phone} missCount={l.miss_count} />
                    </div>
                  </td>
                  <td className="cell-tight"><span className={`src ${srcClass(l.source)}`}>{srcLabel(l.source)}</span></td>
                  {rejected ? (
                    <>
                      <td className="reason-cell"><span className="stage lost">{l.reject_reason || "—"}</span></td>
                      {/* clamped to two lines; the full note is in the tooltip and
                          on the lead itself — a table row is not where it is read */}
                      <td className="note-cell">
                        <div className="note-clamp" title={l.reject_notes || undefined}>{l.reject_notes || "—"}</div>
                      </td>
                      <td style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--muted)", whiteSpace: "nowrap" }}>{l.received_at ? formatDate(l.received_at) : "—"}</td>
                      <td style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--muted)", whiteSpace: "nowrap" }}>{l.rejected_at ? formatDate(l.rejected_at) : "—"}</td>
                    </>
                  ) : (
                    <>
                      {showStage && (
                        <td>{l.visit_status
                          ? <VisitsCell leadId={l.id} status={l.visit_status} date={l.visit_date} society={l.visit_society} rm={l.visit_rm} count={l.visit_count} />
                          : <StageChip stage={l.stage} />}</td>
                      )}
                      <td style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{l.society || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                    </>
                  )}
                  <td onClick={(e) => e.stopPropagation()}><NotesCell leadId={l.id} latest={l.latest_note} count={l.note_count} /></td>
                  <td onClick={(e) => e.stopPropagation()}><AssignControl leadId={l.id} assignedTo={l.assigned_to} /></td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {!rejected && (
                      <button className="btn ghost sm" title="Plan site visits"
                        onClick={(e) => { e.stopPropagation(); setPlanner(l); }}>
                        <IconCalendar /> {bookLabel}
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>
      </div>
      {planner && (
        <VisitPlanner leadId={planner.id} leadName={planner.name} leadCity={planner.city} leadPhone={planner.phone} onClose={() => setPlanner(null)} />
      )}
    </>
  );
}
