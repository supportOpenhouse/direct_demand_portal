import { useQueryClient } from '@tanstack/react-query';
import { NavLink } from 'react-router-dom';
import { useBuckets, useMetrics } from '../lib/queries';
import { useAuth } from '../store/auth';
import { Avatar } from './Avatar';
import {
  IconConverted,
  IconDashboard,
  IconGoldmine,
  IconInventory,
  IconLeads,
  IconPipeline,
  IconQualified,
  IconSettings,
  IconSociety,
  IconSupply,
  OpenhouseLogo,
} from './icons';

function navClass({ isActive }: { isActive: boolean }) {
  return `nav-item${isActive ? ' active' : ''}`;
}

/**
 * Dark 248px sidebar: brand, WORKSPACE / DISCOVERY / ADMIN nav groups with
 * live count badges, user chip at the bottom (click = log out).
 * Gold Mine: admin + cm only. Settings: admin only.
 */
export function Sidebar() {
  const { user, logout } = useAuth();
  const qc = useQueryClient();
  const { data: metrics } = useMetrics();
  const canGoldmine = user?.role === 'admin' || user?.role === 'cm';
  const { data: buckets } = useBuckets({ enabled: canGoldmine });

  const handleLogout = () => {
    logout();
    qc.clear();
  };

  const count = (n: number | undefined) => (n !== undefined && n > 0 ? n : null);

  return (
    <aside className="sidebar">
      <div className="brand">
        <OpenhouseLogo size={38} />
        <div>
          <div className="b-name">Openhouse</div>
          <div className="b-sub">Direct Demand</div>
        </div>
      </div>

      <div className="nav-label">Workspace</div>
      <NavLink to="/" end className={navClass}>
        <IconDashboard />
        <span>Dashboard</span>
      </NavLink>
      <NavLink to="/leads/new" className={navClass}>
        <IconLeads />
        <span>New Leads</span>
        {count(metrics?.new) !== null && <span className="badge">{metrics?.new}</span>}
      </NavLink>
      <NavLink to="/leads/qualified" className={navClass}>
        <IconQualified />
        <span>Qualified Leads</span>
        {count(metrics?.qualified) !== null && (
          <span className="badge soft">{metrics?.qualified}</span>
        )}
      </NavLink>
      <NavLink to="/leads/pipeline" className={navClass}>
        <IconPipeline />
        <span>Pipeline Leads</span>
        {count(metrics?.pipeline) !== null && (
          <span className="badge soft">{metrics?.pipeline}</span>
        )}
      </NavLink>
      <NavLink to="/leads/converted" className={navClass}>
        <IconConverted />
        <span>Converted Leads</span>
        {count(metrics?.converted) !== null && (
          <span className="badge soft">{metrics?.converted}</span>
        )}
      </NavLink>

      <div className="nav-label">Discovery</div>
      <NavLink to="/inventory" className={navClass}>
        <IconInventory />
        <span>Live Inventory</span>
      </NavLink>
      <NavLink to="/supply" className={navClass}>
        <IconSupply />
        <span>Supply Pipeline</span>
      </NavLink>
      <NavLink to="/societies" className={navClass}>
        <IconSociety />
        <span>Society Insights</span>
      </NavLink>
      {canGoldmine && (
        <NavLink to="/goldmine" className={navClass}>
          <IconGoldmine />
          <span>Gold Mine</span>
          {buckets !== undefined && buckets.length > 0 && (
            <span className="badge gold">{buckets.length}</span>
          )}
        </NavLink>
      )}

      {user?.role === 'admin' && (
        <>
          <div className="nav-label">Admin</div>
          <NavLink to="/settings" className={navClass}>
            <IconSettings />
            <span>Settings &amp; Access</span>
          </NavLink>
        </>
      )}

      {user && (
        <div className="user-chip" onClick={handleLogout} title="Click to log out">
          <Avatar name={user.name} size={32} />
          <div className="uc-info">
            <div className="uc-name">{user.name}</div>
            <div className="uc-sub">{user.team_name ?? user.email}</div>
          </div>
          <span className="role-chip">{user.role.toUpperCase()}</span>
        </div>
      )}
    </aside>
  );
}
