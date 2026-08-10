/* 1:1 port of the prototype's <aside class="sidebar"> markup. */
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { useDevUserList } from "../lib/queries";
import { isDevBuild } from "../lib/api";
import { useLeadCounts } from "../lib/queries";
import {
  OpenhouseLogo,
  IconDashboard,
  IconPlus,
  IconQualified,
  IconFunnel,
  IconCheckCircle,
  IconHome,
  IconBox,
  IconBars,
  IconStar,
  IconSettings,
  IconReject,
} from "./icons";

const navClass = ({ isActive }: { isActive: boolean }) => "nav-item" + (isActive ? " active" : "");

/* Share of the role-scoped total this segment holds. Intentionally omitted for
   "new" (per product), and hidden until there's a nonzero total to divide by. */
function Pct({ seg }: { seg: string }) {
  const { data } = useLeadCounts();
  const total = data?.total ?? 0;
  if (!total) return null;
  const p = Math.round(((data!.counts[seg] ?? 0) / total) * 100);
  return (
    <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)", fontVariantNumeric: "tabular-nums" }}>
      {p}%
    </span>
  );
}

/* New Leads shows "{new} | {total}" (non-test total) instead of a % — per product. */
function NewCount() {
  const { data } = useLeadCounts();
  if (data?.status !== "ok") return null;
  return (
    <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)", fontVariantNumeric: "tabular-nums" }}>
      {(data.counts.new ?? 0).toLocaleString("en-IN")} | {data.total_nontest.toLocaleString("en-IN")}
    </span>
  );
}

const IconLogs = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6M8 13h8M8 17h6" />
  </svg>
);

export const IconFollowup = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="13" r="8" /><path d="M12 9v4l2 2M9 2h6" />
  </svg>
);

/* also used by the mobile drawer */
export const IconRnr = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91" />
    <line x1="23" y1="1" x2="1" y2="23" />
  </svg>
);

const IconDialer = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91" />
    <path d="M16 3h5v5" /><path d="M21 3l-6 6" />
  </svg>
);

export default function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  // Auto Dialer's sub-pages only unfold once you're inside it — the Admin section
  // stays a flat list from everywhere else.
  const inDialer = useLocation().pathname.startsWith("/dialer");
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo">
          <OpenhouseLogo />
        </div>
        <div>
          <div className="nm">Openhouse</div>
          <div className="sub">Direct&nbsp;Demand</div>
        </div>
      </div>
      <button
        className="nav-collapse"
        onClick={onToggle}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round">
          <path d={collapsed ? "M9 18l6-6-6-6" : "M15 18l-6-6 6-6"} />
        </svg>
      </button>
      <nav id="nav">
        <div className="nav-label">Workspace</div>
        <NavLink to="/" end className={navClass} title="Dashboard">
          <IconDashboard /> <span className="nav-t">Dashboard</span>
        </NavLink>
        {/* Live Calls sits in the Topbar next to WhatsApp — it's glanced at mid-call,
            not navigated to from a list. */}
        <NavLink to="/leads/new" className={navClass} title="New Leads">
          <IconPlus /> <span className="nav-t">New Leads</span> <NewCount />
        </NavLink>
        <NavLink to="/leads/call-not-received" className={navClass} title="Call Not Received">
          <IconRnr /> <span className="nav-t">Call Not Received</span> <Pct seg="call_not_received" />
        </NavLink>
        <NavLink to="/leads/followup" className={navClass} title="Follow Up">
          <IconFollowup /> <span className="nav-t">Follow Up</span> <Pct seg="followup" />
        </NavLink>
        <NavLink to="/leads/qualified" className={navClass} title="Qualified Leads">
          <IconQualified /> <span className="nav-t">Qualified Leads</span> <Pct seg="qualified" />
        </NavLink>
        <NavLink to="/leads/pipeline" className={navClass} title="Pipeline Leads">
          <IconFunnel /> <span className="nav-t">Pipeline Leads</span> <Pct seg="pipeline" />
        </NavLink>
        <NavLink to="/leads/converted" className={navClass} title="Converted Leads">
          <IconCheckCircle /> <span className="nav-t">Converted Leads</span> <Pct seg="converted" />
        </NavLink>
        {/* RNR has no page of its own — those leads sit in Rejected, badged */}
        <NavLink to="/leads/rejected" className={navClass} title="Rejected Leads">
          <IconReject /> <span className="nav-t">Rejected Leads</span> <Pct seg="rejected" />
        </NavLink>
        <div className="nav-label">Discovery</div>
        <NavLink to="/inventory" className={navClass} title="Live Inventory">
          <IconHome /> <span className="nav-t">Live Inventory</span>
        </NavLink>
        <NavLink to="/supply" className={navClass} title="Supply Pipeline">
          <IconBox /> <span className="nav-t">Supply Pipeline</span>
        </NavLink>
        <NavLink to="/societies" className={navClass} title="Society Insights">
          <IconBars /> <span className="nav-t">Society Insights</span>
        </NavLink>
        <NavLink to="/goldmine" className={navClass} title="Gold Mine">
          <IconStar /> <span className="nav-t">Gold Mine</span>
        </NavLink>
        <div className="nav-label">Admin</div>
        {isAdmin && (
          <>
            {/* The parent is a link too, not just a header — /dialer redirects to
                Schedule Campaign, so clicking it lands somewhere real. */}
            <NavLink to="/dialer" className={navClass} title="Auto Dialer">
              <IconDialer /> <span className="nav-t">Auto Dialer</span>
            </NavLink>
            {inDialer && (
              <div className="nav-sub">
                <NavLink to="/dialer/schedule" className={navClass} title="Schedule Campaign">
                  <span className="nav-t">Schedule Campaign</span>
                </NavLink>
                <NavLink to="/dialer/previous" className={navClass} title="Previous Campaigns">
                  <span className="nav-t">Previous Campaigns</span>
                </NavLink>
              </div>
            )}
          </>
        )}
        <NavLink to="/settings" className={navClass} title="Settings & Access">
          <IconSettings /> <span className="nav-t">Settings &amp; Access</span>
        </NavLink>
        {isAdmin && (
          <NavLink to="/call-log" className={navClass} title="Bonvoice Call Log">
            <IconRnr /> <span className="nav-t">Bonvoice Call Log</span>
          </NavLink>
        )}
        {isAdmin && (
          <NavLink to="/logs" className={navClass} title="Activity Logs">
            <IconLogs /> <span className="nav-t">Activity Logs</span>
          </NavLink>
        )}
      </nav>
      {/* no spacer — #nav is flex:1 and pushes the chip down on its own */}
      <UserChip />
    </aside>
  );
}

/* Local-only identity switcher. The whole component collapses to the plain chip in a
   production build — isDevBuild is compile-time, so the user list and the switching
   code aren't in the deployed bundle at all. */
function DevViewAs({ current, onPick, busy }: {
  current: string | null; onPick: (e: string | null) => void; busy: boolean;
}) {
  const q = useDevUserList(isDevBuild);
  const users = q.data?.items ?? [];
  return (
    <select
      className="dev-viewas"
      value={current ?? ""}
      onClick={(e) => e.stopPropagation()}   // the chip itself is a sign-out button
      onChange={(e) => onPick(e.target.value || null)}
      // the server resolves the email against the users table, which is a Neon
      // round trip — without this the old identity just sits there for a beat
      disabled={busy}
      title="Local only — view the app as another user. Each tab is independent."
    >
      <option value="">{busy ? "switching…" : "View as… (open admin)"}</option>
      {/* say why it's empty rather than showing a lone placeholder that looks broken */}
      {!users.length && (
        <option value="" disabled>
          {q.isLoading ? "loading users…" : q.isError ? "couldn't reach the API" : "no active users"}
        </option>
      )}
      {users.filter((u) => u.active).map((u) => (
        <option key={u.id} value={u.email}>{u.name || u.email} · {u.role}</option>
      ))}
    </select>
  );
}

function UserChip() {
  const { enabled, user, logout, devUser, viewAs, loading } = useAuth();
  const switcher = isDevBuild
    ? <DevViewAs current={devUser} onPick={viewAs} busy={!!devUser && loading} />
    : null;
  if (enabled && user) {
    const init = (user.name || user.email).split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase();
    return (
      <>
      <div className="user" onClick={logout} title="Sign out">
        {user.picture ? (
          <img className="av" src={user.picture} alt="" style={{ objectFit: "cover" }} />
        ) : (
          <div className="av">{init}</div>
        )}
        <div style={{ minWidth: 0 }}>
          <div className="un" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {user.name || user.email}
          </div>
          <div className="ur">Sign out</div>
        </div>
        <span className="role-chip" style={{ textTransform: "capitalize" }}>{user.role}</span>
      </div>
      {switcher}
      </>
    );
  }
  return (
    <>
    <div className="user">
      <div className="av">AD</div>
      <div>
        <div className="un">Admin</div>
        <div className="ur">Openhouse Direct</div>
      </div>
      <span className="role-chip">Admin</span>
    </div>
    {switcher}
    </>
  );
}
