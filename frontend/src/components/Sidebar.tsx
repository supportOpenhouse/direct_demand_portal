/* 1:1 port of the prototype's <aside class="sidebar"> markup. */
import { NavLink } from "react-router-dom";
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
} from "./icons";

const navClass = ({ isActive }: { isActive: boolean }) => "nav-item" + (isActive ? " active" : "");

export default function Sidebar() {
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
      </nav>
      <div className="spacer"></div>
      <div className="user">
        <div className="av">AD</div>
        <div>
          <div className="un">Admin</div>
          <div className="ur">Openhouse Direct</div>
        </div>
        <span className="role-chip">Admin</span>
      </div>
    </aside>
  );
}
