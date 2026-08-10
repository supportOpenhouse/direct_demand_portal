/* Mobile shell. A phone gets its own route table (picked in main.tsx) rather than a
   responsive squeeze of the desktop tables: the worklists here are a name/phone/society
   card list, and everything else (lead detail, inventory) reuses the desktop page. */
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useLeads } from "./lib/queries";
import { leadMatchesQuery, srcClass, srcLabel, stageClass, stageLabel } from "./lib/leads";
import { useSearch } from "./components/SearchContext";
import { useAuth } from "./components/AuthContext";
import GlobalSearch from "./components/GlobalSearch";
import { IconFollowup, IconRnr } from "./components/Sidebar";
import {
  IconSearch, OpenhouseLogo, IconDashboard, IconPlus, IconQualified,
  IconFunnel, IconCheckCircle, IconReject, IconHome,
} from "./components/icons";

export const MOBILE_NAV = [
  { to: "/", label: "Dashboard", end: true, icon: IconDashboard },
  { to: "/leads/new", label: "New Leads", seg: "new", icon: IconPlus },
  { to: "/leads/call-not-received", label: "Call Not Received", seg: "call_not_received", icon: IconRnr },
  { to: "/leads/followup", label: "Follow Up", seg: "followup", icon: IconFollowup },
  { to: "/leads/qualified", label: "Qualified Leads", seg: "qualified", icon: IconQualified },
  { to: "/leads/pipeline", label: "Pipeline Leads", seg: "pipeline", icon: IconFunnel },
  { to: "/leads/converted", label: "Converted Leads", seg: "converted", icon: IconCheckCircle },
  { to: "/leads/rejected", label: "Rejected Leads", seg: "rejected", icon: IconReject },
  { to: "/inventory", label: "Live Inventory", icon: IconHome },
];

/* Signing out drops the session — never on a single mis-tap in a drawer. */
function LogoutConfirm({ onCancel, onYes }: { onCancel: () => void; onYes: () => void }) {
  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="modal" style={{ maxWidth: 320 }}>
        <div className="mb" style={{ fontSize: 15, fontWeight: 600 }}>Do you want to Log Out?</div>
        <div className="mf">
          <button className="btn ghost" onClick={onCancel}>Cancel</button>
          <button className="btn" style={{ background: "var(--coral)", color: "#fff" }} onClick={onYes}>Yes</button>
        </div>
      </div>
    </div>
  );
}

function DrawerUser() {
  const { user, logout } = useAuth();
  const [asking, setAsking] = useState(false);
  const name = user?.name || user?.email || "Admin";
  const init = name.split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase();
  return (
    <>
      <div className="user" onClick={() => setAsking(true)}>
        {user?.picture
          ? <img className="av" src={user.picture} alt="" style={{ objectFit: "cover" }} />
          : <div className="av">{init}</div>}
        <div style={{ minWidth: 0 }}>
          <div className="un" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
          <div className="ur">Log out</div>
        </div>
      </div>
      {asking && <LogoutConfirm onCancel={() => setAsking(false)} onYes={logout} />}
    </>
  );
}

export default function MobileApp() {
  const [drawer, setDrawer] = useState(false);
  const [searching, setSearching] = useState(false);
  const { pathname } = useLocation();
  const { setQuery } = useSearch();
  const title = MOBILE_NAV.find((n) => n.to === pathname)?.label ?? "Lead";

  // landing on a page (including from a search hit) ends the search — otherwise the
  // list underneath stays filtered by a box that's scrolled out of mind
  useEffect(() => { setSearching(false); setQuery(""); }, [pathname, setQuery]);

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
        <div className={"m-search" + (searching ? " open" : "")}><GlobalSearch openLead /></div>
        <button className="m-icon" onClick={toggleSearch} aria-label={searching ? "Close search" : "Search"}>
          {searching ? "✕" : <IconSearch />}
        </button>
      </header>

      <div className="m-view"><Outlet /></div>

      {drawer && <div className="m-scrim" onClick={() => setDrawer(false)} />}
      <aside className={"m-drawer" + (drawer ? " open" : "")}>
        <div className="brand" style={{ marginBottom: 10 }}>
          <div className="logo"><OpenhouseLogo /></div>
          <div>
            <div className="nm">Openhouse</div>
            <div className="sub">Direct&nbsp;Demand</div>
          </div>
        </div>
        <nav style={{ flex: 1, overflowY: "auto" }}>
          {MOBILE_NAV.map(({ to, label, end, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => "nav-item" + (isActive ? " active" : "")}
              onClick={() => setDrawer(false)}
            >
              <Icon /> <span className="nav-t">{label}</span>
            </NavLink>
          ))}
        </nav>
        <DrawerUser />
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
          <div className="m-row-line">
            <span className="m-nm">{l.name || "Unknown lead"}</span>
            <span className={`src ${srcClass(l.source)}`}>{srcLabel(l.source)}</span>
          </div>
          <div className="m-row-line">
            <span className="m-ph">{l.phone || "—"}</span>
            {l.society && <span className="m-soc">{l.society}</span>}
            <span className={`stage ${stageClass(l.stage)}`} style={{ marginLeft: "auto" }}>{stageLabel(l.stage)}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
