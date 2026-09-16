/* New Leads — 1:1 with the prototype's tplNewLeads(), wired to GET /v1/leads?segment=new.
   Two source categories (Meta + listing portals) land in one table; rows clickable → lead detail. */
import { formatDate, formatDateTime, useAllSocieties, useAssignees, useLeadCounts, useLeads, useSyncLeads } from "../lib/queries";
import { Lead } from "../lib/api";
import { isNewToday, leadMatchesQuery, newFirst, planClass, sourcesLabel } from "../lib/leads";
import { ArrivalCount, SourceChips } from "../components/StageChip";
import { sourceMatches, sourceOptions } from "../lib/leadFilters";
import { useAuth } from "../components/AuthContext";
import { useToast } from "../components/Toast";
import { DATE_PRESETS, rmOptions } from "../components/Filters";
import { uniqueValues, countedOptions, matchesOption, inDatePreset, type DatePreset } from "../components/Filters";
import { EXTRA_DEFAULTS, extraFields, passExtras } from "../lib/leadFilters";
import { NotesCell } from "../components/NotesCell";
import { CallButton } from "../components/CallButton";
import LeadPhone from "../components/LeadPhone";
import { AssignControl } from "../components/AssignControl";
import { useSort, SortTh } from "../lib/useSort";
import { ExportCsvButton } from "../components/ExportCsvButton";
import { useRowSelection } from "../lib/useRowSelection";
import { BulkAssignBar } from "../components/BulkAssignBar";
import { useState } from "react";
import { SkeletonTable } from "../components/Skeleton";
import { useFilterValues } from "../components/FilterBar";
import { LeadToolbar, cityMatches } from "../components/LeadToolbar";
import { IconRefresh } from "../components/icons";
import { TopbarSlot } from "../components/TopbarSlot";
import { Pager, usePaging } from "../components/Pager";
import { useRowOpen } from "../components/LeadModal";
import { NewBadge } from "../components/StageChip";

function PlanChip({ plan }: { plan: string | null }) {
  if (!plan) return <span style={{ color: "var(--muted)" }}>—</span>;
  return <span className={`plan-chip ${planClass(plan)}`}>{plan}</span>;
}

export default function NewLeads() {
  const { data, isLoading } = useLeads("new");
  const { data: counts } = useLeadCounts();
  // Page-local search and city tab. Local on purpose: a query that outlives the
  // page it was typed on is what the global box got wrong.
  const [q, setQ] = useState("");
  const [cityTab, setCityTab] = useState("");
  const [selectMode, setSelectMode] = useState(false);
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  const toast = useToast();
  const sync = useSyncLeads();
  const runSync = () =>
    sync.mutate(undefined, {
      onSuccess: (r) => {
        const added = (r.meta_new ?? 0) + (r.listing_new ?? 0);
        toast(added ? `Synced · ${added} new lead${added > 1 ? "s" : ""}` : "Synced · no new leads", "green");
      },
      onError: (e) => toast(e.message, "gold"),
    });
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
  const { sorted: sortedRows, sortKey, dir, onSort } = useSort<Lead>(filtered, {
    name: (l) => l.name,
    phone: (l) => l.phone,
    source: (l) => sourcesLabel(l),
    city: (l) => l.city,
    society: (l) => l.society,
    budget: (l) => l.budget_band,
    plan: (l) => l.plan_to_buy,
    date: (l) => (l.received_at ? Date.parse(l.received_at) : null),
    assigned: (l) => l.assigned_to,
    notes: (l) => (l.latest_note_at ? Date.parse(l.latest_note_at) : null),
    activity: (l) => (l.latest_activity_at ? Date.parse(l.latest_activity_at) : null),
  });
  // NEW-badge leads on top, the chosen sort within each group
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
        <ExportCsvButton leads={list} name="new-leads" />
      </TopbarSlot>
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
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {isAdmin && (
            <button className="btn ghost sm" disabled={sync.isPending} onClick={runSync}
              title="Pull new leads from the Google Sheets now (runs automatically at 11:30 AM & 2 PM IST)">
              {sync.isPending ? "Syncing…" : <><IconRefresh /> Sync now</>}
            </button>
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
              <SortTh label="City" sortKey="city" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Society (from source)" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Budget" sortKey="budget" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Plan to Buy" sortKey="plan" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Created On" sortKey="date" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Assigned To" sortKey="assigned" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Notes" sortKey="notes" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Latest activity" sortKey="activity" activeKey={sortKey} dir={dir} onSort={onSort} />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <SkeletonTable rows={8} cols={11 + (selectMode ? 1 : 0)} />
            ) : list.length === 0 ? (
              <tr>
                <td colSpan={11 + (selectMode ? 1 : 0)}>
                  <div className="empty" style={{ padding: 24 }}>
                    {all.length === 0 ? "No new leads right now." : "No leads match the search / filters."}
                  </div>
                </td>
              </tr>
            ) : (
              pg.slice.map((l) => (
                <tr key={l.id} {...rowOpen(l.id)}>
                  {selectMode && (
                    <td onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={sel.has(l.id)} onChange={() => sel.toggle(l.id)} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} />
                    </td>
                  )}
                  <td className="lead-cell" title={l.name ?? ""}>
                        <div className="nm">
                          {isNewToday(l) && <NewBadge size={18} style={{ marginRight: 6 }} />}
                          {l.name}<ArrivalCount lead={l} />
                          {l.is_test && (
                            <span className="bucket-tag" style={{ marginLeft: 6 }}>TEST</span>
                          )}
                        </div>
                  </td>
                  <td className="ph-cell" onClick={(e) => e.stopPropagation()}>
                    <div className="phone-cell">
                      <CallButton leadId={l.id} disabled={!l.phone} />
                      <LeadPhone phone={l.phone} missCount={l.miss_count} />
                    </div>
                  </td>
                  <td className="cell-tight"><SourceChips lead={l} /></td>
                  <td className="cell-tight" style={{ fontSize: 12.5 }}>{l.city || "—"}</td>
                  <td className="cell-text" style={{ fontSize: 12.5, color: "var(--ink-2)" }} title={l.society || ""}><span>{l.society || "—"}</span></td>
                  <td className="cell-tight" style={{ fontSize: 12.5 }}>{l.budget_band || "—"}</td>
                  <td><PlanChip plan={l.plan_to_buy} /></td>
                  <td className="cell-tight" style={{ fontSize: 12.5, fontFamily: "var(--font-mono)" }}>{formatDate(l.received_at)}</td>
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
