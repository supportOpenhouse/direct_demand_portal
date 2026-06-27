/* New Leads — 1:1 with the prototype's tplNewLeads(), wired to GET /v1/leads?segment=new.
   Two source categories (Meta + listing portals) land in one table; rows clickable → lead detail. */
import { useNavigate } from "react-router-dom";
import { useLeads, formatDate } from "../lib/queries";
import { Lead } from "../lib/api";
import { srcLabel, planClass, initials } from "../lib/leads";
import { useSearch, matches } from "../components/SearchContext";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { NotesCell } from "../components/NotesCell";
import { CallConnected } from "../components/CallConnected";
import { AssignControl } from "../components/AssignControl";
import { useSort, SortTh } from "../lib/useSort";
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
  const nav = useNavigate();
  const { query } = useSearch();
  const [source, setSource] = useState("");
  const [city, setCity] = useState("");
  const [owner, setOwner] = useState("");
  const [plan, setPlan] = useState("");

  const all = data?.items ?? [];
  const filtered = all.filter(
    (l) =>
      (!source || l.source === source) &&
      (!city || l.city === city) &&
      (!plan || l.plan_to_buy === plan) &&
      (!owner || (owner === "Unassigned" ? !l.assigned_to : l.assigned_to === owner)) &&
      matches(query, l.name, l.phone, l.city, l.society, l.budget_band, srcLabel(l.source))
  );
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
        <p className="sec-sub" style={{ margin: 0 }}>
          Untouched leads still inside their first-contact window (TAT) — call before it lapses.
          {data?.status === "ok" && (
            <>
              {" "}
              <b style={{ color: "var(--ink-2)" }}>
                {list.length !== all.length ? `${list.length} of ${all.length}` : all.length}
              </b>{" "}
              new
            </>
          )}
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <FilterSelect label="Source" value={source} options={uniqueValues(all, (l) => l.source).map(srcLabel)}
            onChange={(v) => setSource(uniqueValues(all, (l) => l.source).find((s) => srcLabel(s) === v) || "")} width={130} />
          <FilterSelect label="City" value={city} options={uniqueValues(all, (l) => l.city)} onChange={setCity} width={120} />
          <FilterSelect label="Plan" value={plan} options={uniqueValues(all, (l) => l.plan_to_buy)} onChange={setPlan} width={130} />
          <FilterSelect label="Owner" value={owner} options={["Unassigned", ...uniqueValues(all, (l) => l.assigned_to)]} onChange={setOwner} width={140} />
          {(source || city || plan || owner) && (
            <button className="btn ghost sm" onClick={() => { setSource(""); setCity(""); setPlan(""); setOwner(""); }}>Clear</button>
          )}
        </div>
      </div>

      <BulkAssignBar ids={sel.activeIds} onDone={sel.clear} />

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
              <SortTh label="Date" sortKey="date" activeKey={sortKey} dir={dir} onSort={onSort} />
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
                      <div className="av">{initials(l.name)}</div>
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
                        <div className="ph">{l.phone}</div>
                      </div>
                    </div>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}><CallConnected leadId={l.id} /></td>
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
    </>
  );
}
