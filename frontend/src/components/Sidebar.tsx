/* 1:1 port of the prototype's <aside class="sidebar"> markup. */
import { NavLink } from "react-router-dom";
import { useAuth } from "./AuthContext";
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

const IconFollowup = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="13" r="8" /><path d="M12 9v4l2 2M9 2h6" />
  </svg>
);

const IconRnr = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91" />
    <line x1="23" y1="1" x2="1" y2="23" />
  </svg>
);

export default function Sidebar() {
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
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
      <nav id="nav">
        <div className="nav-label">Workspace</div>
        <NavLink to="/" end className={navClass}>
          <IconDashboard /> Dashboard
        </NavLink>
        <NavLink to="/leads/new" className={navClass}>
          <IconPlus /> New Leads <NewCount />
        </NavLink>
        <NavLink to="/leads/followup" className={navClass}>
          <IconFollowup /> Follow-up <Pct seg="followup" />
        </NavLink>
        <NavLink to="/leads/qualified" className={navClass}>
          <IconQualified /> Qualified Leads <Pct seg="qualified" />
        </NavLink>
        <NavLink to="/leads/pipeline" className={navClass}>
          <IconFunnel /> Pipeline Leads <Pct seg="pipeline" />
        </NavLink>
        <NavLink to="/leads/converted" className={navClass}>
          <IconCheckCircle /> Converted Leads <Pct seg="converted" />
        </NavLink>
        <NavLink to="/leads/rnr" className={navClass}>
          <IconRnr /> RNR <Pct seg="rnr" />
        </NavLink>
        <NavLink to="/leads/rejected" className={navClass}>
          <IconReject /> Rejected Leads <Pct seg="rejected" />
        </NavLink>
        <div className="nav-label">Discovery</div>
        <NavLink to="/inventory" className={navClass}>
          <IconHome /> Live Inventory
        </NavLink>
        <NavLink to="/supply" className={navClass}>
          <IconBox /> Supply Pipeline
        </NavLink>
        <NavLink to="/societies" className={navClass}>
          <IconBars /> Society Insights
        </NavLink>
        <NavLink to="/goldmine" className={navClass}>
          <IconStar /> Gold Mine
        </NavLink>
        <div className="nav-label">Admin</div>
        <NavLink to="/settings" className={navClass}>
          <IconSettings /> Settings &amp; Access
        </NavLink>
        {isAdmin && (
          <NavLink to="/logs" className={navClass}>
            <IconLogs /> Activity Logs
          </NavLink>
        )}
      </nav>
      <div className="spacer"></div>
      <UserChip />
    </aside>
  );
}

function UserChip() {
  const { enabled, user, logout } = useAuth();
  if (enabled && user) {
    const init = (user.name || user.email).split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase();
    return (
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
    );
  }
  return (
    <div className="user">
      <div className="av">AD</div>
      <div>
        <div className="un">Admin</div>
        <div className="ur">Openhouse Direct</div>
      </div>
      <span className="role-chip">Admin</span>
    </div>
  );
}
