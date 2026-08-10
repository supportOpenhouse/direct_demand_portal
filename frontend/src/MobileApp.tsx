/* Mobile shell. A phone gets its own route table (picked in main.tsx) rather than a
   responsive squeeze of the desktop tables — the worklists here are name + phone only
   and the lead view is read-only. Shell + both pages live in one file on purpose. */
import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { useLead, useLeads, formatDate, formatDateTime } from "./lib/queries";
import { leadMatchesQuery, srcLabel, stageLabel } from "./lib/leads";
import { useSearch } from "./components/SearchContext";
import GlobalSearch from "./components/GlobalSearch";
import { IconSearch, OpenhouseLogo } from "./components/icons";

export const MOBILE_NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/leads/new", label: "New Leads", seg: "new" },
  { to: "/leads/call-not-received", label: "Call Not Received", seg: "call_not_received" },
  { to: "/leads/followup", label: "Follow Up", seg: "followup" },
  { to: "/leads/qualified", label: "Qualified Leads", seg: "qualified" },
  { to: "/leads/pipeline", label: "Pipeline Leads", seg: "pipeline" },
  { to: "/leads/converted", label: "Converted Leads", seg: "converted" },
  { to: "/leads/rejected", label: "Rejected Leads", seg: "rejected" },
];

export default function MobileApp() {
  const [drawer, setDrawer] = useState(false);
  const [searching, setSearching] = useState(false);
  const { pathname } = useLocation();
  const { setQuery } = useSearch();
  const title = MOBILE_NAV.find((n) => n.to === pathname)?.label ?? "Lead";

  // closing clears the query — otherwise the list stays filtered by a box you can't see
  const toggleSearch = () => {
    if (searching) { setQuery(""); setSearching(false); return; }
    setSearching(true);
    document.querySelector<HTMLInputElement>(".m-search input")?.focus();
  };

  return (
    <div className="m-app">
      <header className="m-top">
        <button className="m-icon" onClick={() => setDrawer(true)} aria-label="Open menu">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 18l6-6-6-6" />
          </svg>
        </button>
        {!searching && <h1 className="m-title">{title}</h1>}
        {/* always mounted so the width transition has something to animate */}
        <div className={"m-search" + (searching ? " open" : "")}><GlobalSearch /></div>
        <button className="m-icon" onClick={toggleSearch} aria-label={searching ? "Close search" : "Search"}>
          {searching ? "✕" : <IconSearch />}
        </button>
      </header>

      <div className="m-view"><Outlet /></div>

      {drawer && <div className="m-scrim" onClick={() => setDrawer(false)} />}
      <aside className={"m-drawer" + (drawer ? " open" : "")}>
        <div className="brand" style={{ marginBottom: 14 }}>
          <div className="logo"><OpenhouseLogo /></div>
          <div>
            <div className="nm">Openhouse</div>
            <div className="sub">Direct&nbsp;Demand</div>
          </div>
        </div>
        {MOBILE_NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) => "m-nav-item" + (isActive ? " active" : "")}
            onClick={() => setDrawer(false)}
          >
            {n.label}
          </NavLink>
        ))}
      </aside>
    </div>
  );
}

export function MobileLeads({ segment }: { segment: string }) {
  const { data, isLoading } = useLeads(segment);
  const { query } = useSearch();
  const nav = useNavigate();
  const list = (data?.items ?? []).filter((l) => leadMatchesQuery(query, l));

  if (isLoading) return <div className="empty">Loading…</div>;
  if (!list.length) return <div className="empty">No leads here.</div>;
  return (
    <div className="m-list">
      {list.map((l) => (
        <button key={l.id} className="m-row" onClick={() => nav(`/leads/${l.id}`)}>
          <span className="m-nm">{l.name || "Unknown lead"}</span>
          <span className="m-ph">{l.phone || "—"}</span>
        </button>
      ))}
    </div>
  );
}

/* Read-only by design — editing stays on desktop, so this is a plain value list
   with no inputs, no actions and nothing that writes back. */
export function MobileLeadDetail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { data: lead, isLoading } = useLead(id);

  if (isLoading) return <div className="empty">Loading lead…</div>;
  if (!lead) return <div className="empty">Lead not found.</div>;

  const c = lead.confirmed_data;
  const captured: [string, string | null][] = [
    ["Phone", lead.phone],
    ["Email", lead.email],
    ["Source", srcLabel(lead.source)],
    ["Stage", stageLabel(lead.stage)],
    ["Assigned to", lead.assigned_to],
    ["City", lead.city],
    ["Society", lead.society],
    ["Budget", lead.budget_band],
    ["Configuration", lead.configuration],
    ["Plan to buy", lead.plan_to_buy],
    ["Received", lead.received_at && formatDateTime(lead.received_at)],
    ["Next follow-up", lead.follow_up_at && formatDateTime(lead.follow_up_at)],
    ["Visit", lead.visit_status && `${lead.visit_status}${lead.visit_date ? ` · ${formatDate(lead.visit_date)}` : ""}`],
    ["Source remarks", lead.source_remarks],
    ["Latest note", lead.latest_note],
    ["Rejected", lead.reject_reason && `${lead.reject_reason}${lead.reject_notes ? ` — ${lead.reject_notes}` : ""}`],
  ];
  const confirmed: [string, string | null][] = c ? [
    ["Purpose", c.purpose],
    ["Budget", c.budget_min_lacs && c.budget_max_lacs ? `₹${c.budget_min_lacs}–${c.budget_max_lacs} lacs` : null],
    ["Configuration", c.configuration],
    ["Size", c.size_min_sqft || c.size_max_sqft ? `${c.size_min_sqft ?? "—"}–${c.size_max_sqft ?? "—"} sq.ft` : null],
    ["Micro-markets", c.preferred_micromarkets.join(", ")],
    ["Preferred localities", c.preferred_localities.join(", ")],
    ["Shortlisted societies", c.shortlisted_societies.join(", ")],
    ["Willing to visit office", c.office_willing],
    ["Preferred office date", c.office_preferred_date],
    ["Remark", c.remark],
  ] : [];

  const rows = (items: [string, string | null][]) =>
    items.filter(([, v]) => !!v).map(([k, v]) => (
      <div key={k}>
        <div className="m-dt">{k}</div>
        <div className="m-dd">{v}</div>
      </div>
    ));

  return (
    <>
      <div className="back" onClick={() => nav(-1)}>← Back</div>
      <div className="m-card">
        <div className="m-nm" style={{ fontSize: 18, marginBottom: 12 }}>
          {lead.name || "Unknown lead"}
          {lead.is_test && <span className="bucket-tag" style={{ marginLeft: 8 }}>TEST</span>}
        </div>
        {rows(captured)}
      </div>
      {confirmed.some(([, v]) => !!v) && (
        <div className="m-card">
          <div className="panel-title">Confirmed on call</div>
          {rows(confirmed)}
        </div>
      )}
    </>
  );
}
