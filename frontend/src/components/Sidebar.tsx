/* 1:1 port of the prototype's <aside class="sidebar"> markup. */
import { NavLink } from "react-router-dom";
import { useAuth } from "./AuthContext";
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

const IconLogs = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6M8 13h8M8 17h6" />
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
          <IconPlus /> New Leads
        </NavLink>
        <NavLink to="/leads/qualified" className={navClass}>
          <IconQualified /> Qualified Leads
        </NavLink>
        <NavLink to="/leads/pipeline" className={navClass}>
          <IconFunnel /> Pipeline Leads
        </NavLink>
        <NavLink to="/leads/converted" className={navClass}>
          <IconCheckCircle /> Converted Leads
        </NavLink>
        <NavLink to="/leads/rejected" className={navClass}>
          <IconReject /> Rejected Leads
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
