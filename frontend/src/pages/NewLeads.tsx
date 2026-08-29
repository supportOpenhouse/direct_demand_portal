/* New Leads — 1:1 with the prototype's tplNewLeads(), wired to GET /v1/leads?segment=new.
   Two source categories (Meta + listing portals) land in one table; rows clickable → lead detail. */
import { useNavigate } from "react-router-dom";
import { useLeads, useLeadCounts, useSyncLeads, formatDate } from "../lib/queries";
import { Lead } from "../lib/api";
import { srcLabel, planClass, leadMatchesQuery } from "../lib/leads";
import { useSearch } from "../components/SearchContext";
import { useAuth } from "../components/AuthContext";
import { useToast } from "../components/Toast";
import { FilterSelect, uniqueValues, countedOptions, matchesOption, DateFilter, inDatePreset, type DatePreset } from "../components/Filters";
import { NotesCell } from "../components/NotesCell";
import { CallConnected } from "../components/CallConnected";
import { CallButton } from "../components/CallButton";
import LeadPhone from "../components/LeadPhone";
import { AssignControl } from "../components/AssignControl";
import { useSort, SortTh } from "../lib/useSort";
import { ExportCsvButton } from "../components/ExportCsvButton";
import { useRowSelection } from "../lib/useRowSelection";
import { BulkAssignBar } from "../components/BulkAssignBar";
import { useState } from "react";

function PlanChip({ plan }: { plan: string | null }) {
  if (!plan) return <span style={{ color: "var(--muted)" }}>—</span>;
  return <span className={`plan-chip ${planClass(plan)}`}>{plan}</span>;
}

// "NEW" = the lead's date (the one shown in the Date column) is today
const isFreshLead = (l: Lead) => {
  if (!l.received_at) return false;
  return new Date(l.received_at).toDateString() === new Date().toDateString();
};

export default function NewLeads() {
  const { data, isLoading } = useLeads("new");
  const { data: counts } = useLeadCounts();
  const nav = useNavigate();
  const { query } = useSearch();
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  const toast = useToast();
  const sync = useSyncLeads();
  const runSync = () =>
    sync.mutate(undefined, {
      onSuccess: (r) => {
        const added = (r.meta_new ?? 0) + (r.listing_new ?? 0);
        toast(added ? `Synced · ${added} new lead${added > 1 ? "s" : ""}` : "Synced · no new leads", "green", "⟳");
      },
      onError: (e) => toast(e.message, "gold", "⚠"),
    });
  const [source, setSource] = useState("");
  const [city, setCity] = useState("");
  const [owner, setOwner] = useState("");
  const [plan, setPlan] = useState("");
  const [datePreset, setDatePreset] = useState<DatePreset>("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // "Plan to buy" is a Meta-form field — irrelevant for listing sources (99acres / MagicBricks)
  const showPlan = source === "meta";
  // switching away from Meta drops the now-hidden plan filter so it can't silently constrain results
  const onSource = (v: string) => {
    setSource(v);
    if (v !== "meta") setPlan("");
  };

  const all = data?.items ?? [];
  // faceted counts: each dropdown counts leads passing all the OTHER filters (skip its own)
  const pass = (l: Lead, skip?: string) =>
    (skip === "source" || !source || l.source === source) &&
    (skip === "city" || matchesOption(l.city, city)) &&
    (!plan || l.plan_to_buy === plan) &&
    (skip === "owner" || matchesOption(l.assigned_to, owner)) &&
    inDatePreset(l.received_at, datePreset, dateFrom, dateTo) &&
    leadMatchesQuery(query, l);
  const filtered = all.filter((l) => pass(l));
  const { sorted: list, sortKey, dir, onSort } = useSort<Lead>(filtered, {
    name: (l) => l.name,
    city: (l) => l.city,
    society: (l) => l.society,
    budget: (l) => l.budget_band,
    plan: (l) => l.plan_to_buy,
    date: (l) => (l.received_at ? Date.parse(l.received_at) : null),
    assigned: (l) => l.assigned_to,
    notes: (l) => (l.latest_note_at ? Date.parse(l.latest_note_at) : null),
  });
  const sel = useRowSelection(list.map((l) => l.id));

  return (
    <>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          {data?.status === "ok" && (
            <>
              <span style={{ fontFamily: "'Bricolage Grotesque'", fontSize: 26, fontWeight: 700, letterSpacing: "-.02em", lineHeight: 1 }}>
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
              {sync.isPending ? "Syncing…" : "⟳ Sync now"}
            </button>
          )}
          <FilterSelect label="Source" value={source}
            options={countedOptions(all.filter((l) => pass(l, "source")), (l) => l.source, "Unknown", srcLabel, source)}
            onChange={onSource} width={150} />
          <FilterSelect label="City" value={city} options={countedOptions(all.filter((l) => pass(l, "city")), (l) => l.city, "No City", undefined, city)} onChange={setCity} width={150} />
          {showPlan && (
            <FilterSelect label="Plan" value={plan} options={uniqueValues(all, (l) => l.plan_to_buy)} onChange={setPlan} width={130} />
          )}
          <FilterSelect label="Owner" value={owner} options={countedOptions(all.filter((l) => pass(l, "owner")), (l) => l.assigned_to, "Unassigned", undefined, owner)} onChange={setOwner} width={160} />
          <DateFilter preset={datePreset} from={dateFrom} to={dateTo} onPreset={setDatePreset} onFrom={setDateFrom} onTo={setDateTo} />
          {(source || city || plan || owner || datePreset) && (
            <button className="btn ghost sm" onClick={() => { setSource(""); setCity(""); setPlan(""); setOwner(""); setDatePreset(""); setDateFrom(""); setDateTo(""); }}>Clear</button>
          )}
          <ExportCsvButton leads={list} name="new-leads" />
        </div>
      </div>

      <BulkAssignBar ids={sel.activeIds} onDone={sel.clear}
        total={sel.visibleCount} onSelectFirst={sel.selectFirst} />

      <div className="card panel-pad" id="needing-action">
        <div className="section-head">
          <div className="panel-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>{" "}
            New Leads: Urgent action required
          </div>
          <button
            className="btn sm"
            style={{ background: "var(--cyan)", color: "#fff", boxShadow: "0 6px 16px -8px var(--cyan)" }}
            onClick={() => nav("/leads/qualified")}
          >
            Qualified Leads →
          </button>
        </div>
        <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 30 }}>
                <input type="checkbox" checked={sel.allChecked} onChange={sel.toggleAll} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} title="Select all" />
              </th>
              <SortTh label="Lead" sortKey="name" activeKey={sortKey} dir={dir} onSort={onSort} />
              <th>Call connected?</th>
              <SortTh label="City" sortKey="city" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Society (from source)" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Budget" sortKey="budget" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Plan to Buy" sortKey="plan" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Created On" sortKey="date" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Assigned To" sortKey="assigned" activeKey={sortKey} dir={dir} onSort={onSort} />
              <SortTh label="Notes" sortKey="notes" activeKey={sortKey} dir={dir} onSort={onSort} />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={10}>
                  <div className="empty" style={{ padding: 24 }}>Loading leads…</div>
                </td>
              </tr>
            ) : list.length === 0 ? (
              <tr>
                <td colSpan={10}>
                  <div className="empty" style={{ padding: 24 }}>
                    {all.length === 0 ? "No new leads right now. 🎉" : "No leads match the search / filters."}
                  </div>
                </td>
              </tr>
            ) : (
              list.map((l) => (
                <tr key={l.id} className="lead-row" style={{ cursor: "default" }}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={sel.has(l.id)} onChange={() => sel.toggle(l.id)} style={{ accentColor: "var(--emerald)", cursor: "pointer" }} />
                  </td>
                  <td>
                    <div className="who">
                      {/* this table had no avatar to replace, but it's the primary
                          calling worklist — the button belongs here most of all */}
                      <CallButton leadId={l.id} disabled={!l.phone} />
                      <div>
                        <div className="nm">
                          {l.name}{" "}
                          <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>
                            ({srcLabel(l.source)})
                          </span>
                          {isFreshLead(l) && (
                            <span style={{ marginLeft: 6, fontSize: 9.5, fontWeight: 800, letterSpacing: ".04em",
                              padding: "1px 6px", borderRadius: 20, background: "var(--emerald)", color: "#fff", verticalAlign: "middle" }}>
                              NEW
                            </span>
                          )}
                          {l.is_test && (
                            <span className="bucket-tag" style={{ marginLeft: 6 }}>TEST</span>
                          )}
                        </div>
                        <LeadPhone phone={l.phone} missCount={l.miss_count} />
                      </div>
                    </div>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}><CallConnected leadId={l.id} lastNoAt={l.last_no_timestamp} /></td>
                  <td style={{ fontSize: 12.5 }}>{l.city || "—"}</td>
                  <td style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{l.society || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                  <td style={{ fontSize: 12.5 }}>{l.budget_band || "—"}</td>
                  <td><PlanChip plan={l.plan_to_buy} /></td>
                  <td style={{ fontSize: 12.5, whiteSpace: "nowrap", fontFamily: "'Spline Sans Mono'" }}>{formatDate(l.received_at)}</td>
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
