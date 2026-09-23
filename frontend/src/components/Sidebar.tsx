/* 1:1 port of the prototype's <aside class="sidebar"> markup. */
import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { useDevUserList } from "../lib/queries";
import { isDevBuild } from "../lib/api";
import { useAppSettings, useIncomingCalls, useLeadCounts, useMyCalls, useWaLatest } from "../lib/queries";
import { isCallingRm } from "../lib/roles";
import { readWaSeenAt } from "../lib/whatsapp";
import { markCallsSeen, readCallsSeenAt } from "../lib/calls";
import {
  IconBox,
  IconCheckCircle,
  IconClock,
  IconFunnel,
  IconHome,
  IconHomeNav,
  IconHuvo,
  IconLiveCall,
  IconMeta,
  IconPlus,
  IconQualified,
  IconReject,
  IconSettings,
  OpenhouseLogo,
  WhatsAppIcon,
} from "./icons";
import { NewBadge } from "./StageChip";
import { useWaAllowed } from "../lib/wa";

/* Bar chart — the report is a table of per-person numbers. */
const IconReport = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 3v18h18" /><path d="M7 15v3M12 10v8M17 6v12" />
  </svg>
);

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
      {/* Both marks stay mounted; CSS shows one. The full lockup is ~4:1 and has no
          business in a 72px rail, so the collapsed rail falls back to the square
          OpenhouseLogo it always used. Alt text on the image only — the icon is
          decorative once the wordmark beside it says the same thing. */}
      <div className="brand">
        <div className="logo">
          <OpenhouseLogo />
        </div>
        {/* Two files, not one filtered file. The lockup is #000000 ink + #2563EA
            "DIRECT DEMAND", and no filter chain lands that blue on the dark-mode
            brand — invert+hue-rotate produced ~#65A3FF. The dark variant is the
            same artwork with the ink remapped to white and the blue to #07b6d4. */}
        <img className="brand-logo light-only" src="/direct_demand_logo.png"
             alt="Openhouse Direct Demand" />
        <img className="brand-logo dark-only" src="/direct_demand_logo_dark.png"
             alt="" aria-hidden="true" />
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
        <NavLink to="/" end className={navClass} title="Home">
          <IconHomeNav /> <span className="nav-t">Home</span>
        </NavLink>
        <NavLink to="/leads/new" className={navClass} title="New Leads">
          <IconPlus /> <span className="nav-t">New Leads</span> <NewCount />
        </NavLink>
        <NavLink to="/leads/call-not-received" className={navClass} title="Call Not Received">
          <IconRnr /> <span className="nav-t">Call Not Received</span> <Pct seg="call_not_received" />
        </NavLink>
        <NavLink to="/leads/followup" className={navClass} title="Call Back Again">
          <IconFollowup /> <span className="nav-t">Call Back Again</span> <Pct seg="followup" />
        </NavLink>
        <NavLink to="/leads/qualified" className={navClass} title="Qualified Leads">
          <IconQualified /> <span className="nav-t">Qualified Leads</span> <Pct seg="qualified" />
        </NavLink>
        {/* parked, not lost — its own page since 16 Sep, so a buyer worth calling in
            three months is no longer filed among dead leads */}
        <NavLink to="/leads/future-prospect" className={navClass} title="Future Prospect">
          <IconClock /> <span className="nav-t">Future Prospect</span> <Pct seg="future_prospect" />
        </NavLink>
        {/* visit_scheduled + revisit_scheduled share this page */}
        <NavLink to="/leads/visited" className={navClass} title="Visited Leads">
          <IconFunnel /> <span className="nav-t">Visited Leads</span> <Pct seg="visited" />
        </NavLink>
        <NavLink to="/leads/rejected" className={navClass} title="Rejected Leads">
          <IconReject /> <span className="nav-t">Rejected Leads</span> <Pct seg="rejected" />
        </NavLink>
        <NavLink to="/leads/converted" className={navClass} title="Converted Leads">
          <IconCheckCircle /> <span className="nav-t">Converted Leads</span> <Pct seg="converted" />
        </NavLink>
        {/* Both were topbar buttons. They're pages, so they belong in the nav — and
            at the END of Workspace: neither is a stage of the funnel above, so
            sitting among the stage pages made the sequence read wrong. */}
        <LiveCallsNav />
        <WhatsAppNav />
        {/* Discovery — Live Inventory + Supply Pipeline, hidden 15 Sep on request.
            Commented out, not deleted: the pages, their CSS and the poster are all
            untouched, so restoring is uncommenting this block and the routes in
            main.tsx. The whole section label goes too — those two were all it held.
        <div className="nav-label">Discovery</div>
        <NavLink to="/inventory" className={navClass} title="Live Inventory">
          <IconHome /> <span className="nav-t">Live Inventory</span>
        </NavLink>
        <NavLink to="/supply" className={navClass} title="Supply Pipeline">
          <IconBox /> <span className="nav-t">Supply Pipeline</span>
        </NavLink>
        */}
        <div className="nav-label">Discovery</div>
        <NavLink to="/demand-dashboard" className={navClass} title="Demand Dashboard">
          <IconBox /> <span className="nav-t">Demand Dashboard</span>
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
        {/* Not admin-gated any more: RMs get the same page scoped to their own
            handset, so it's their record of who they spoke to. */}
        <CallLogNav />
        {/* Its sibling: same shape of page, different provider. Bonvoice logs the
            telephony leg, Huvo logs what was said on it. */}
        {isAdmin && (
          <NavLink to="/huvo-calls" className={navClass} title="Huvo Call Log">
            <IconHuvo />
            <span className="nav-t">Huvo Call Log</span>
          </NavLink>
        )}
        {/* Meta lead-ads deliveries. Admin-only both here and server-side: it's a
            record of what arrived from Meta, not a worklist anyone owns. */}
        {isAdmin && (
          <NavLink to="/meta-leads" className={navClass} title="Meta Leads">
            <IconMeta /> <span className="nav-t">Meta Leads</span>
          </NavLink>
        )}
        {/* Admin-only in the nav; the endpoint itself scopes an RM to their own row,
            so an RM reaching it directly sees themselves rather than a league table. */}
        {isAdmin && (
          <NavLink to="/reports" className={navClass} title="Reports">
            <IconReport /> <span className="nav-t">Reports</span>
          </NavLink>
        )}
        {isAdmin && (
          <NavLink to="/logs" className={navClass} title="Activity Logs">
            <IconLogs /> <span className="nav-t">Activity Logs</span>
          </NavLink>
        )}
        {/* Last in the section: the one entry nobody navigates to as part of the
            day's work. Admin-only in the nav — the page itself already refuses a
            non-admin, so this just stops advertising a door that won't open. */}
        {isAdmin && (
          <NavLink to="/settings" className={navClass} title="Settings & Access">
            <IconSettings /> <span className="nav-t">Settings &amp; Access</span>
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

/* RMs only. Admins run campaigns, they don't take the calls, so this would be
   permanently dead chrome for them. Note the consequence: an admin who IS in a
   campaign's RM pool gets rung with no way to reach this page or mark the result. */
function LiveCallsNav() {
  // `!enabled` keeps the gate biting while impersonating.
  // test_rm counts: a test RM takes real calls and has to mark the results.
  const { enabled, user } = useAuth();
  const isRm = enabled && isCallingRm(user?.role);
  // Hook order can't depend on a condition, so always call it and gate on `isRm`.
  const { data } = useMyCalls(true, isRm);   // the page owns polling; this reads cache
  if (!isRm) return null;

  const live = !!data?.now_calling;
  const unmarked = (data?.completed || []).filter((c) => !c.call_result).length;
  return (
    <NavLink to="/live-calls" className={navClass} title="Live Calls">
      <IconLiveCall /> <span className="nav-t">Live Calls</span>
      {live ? <span className="badge">LIVE</span>
        : unmarked > 0 ? <span className="badge gold">{unmarked}</span> : null}
    </NavLink>
  );
}

/* Admins always; RMs only when an admin has enabled WhatsApp for all RMs or for
   this specific person. */
function WhatsAppNav() {
  const { pathname } = useLocation();
  const allowed = useWaAllowed();

  // "Unseen" = an inbound message newer than the last time this browser opened the
  // WhatsApp page. Per-browser via localStorage rather than a read-receipt table —
  // one person watching the inbox is the actual use case here.
  const { data: latest } = useWaLatest(allowed);
  const unseen = !!latest?.last_inbound_at && +new Date(latest.last_inbound_at) > readWaSeenAt()
    && pathname !== "/chat";
  if (!allowed) return null;
  return (
    <NavLink to="/chat" className={navClass} title="WhatsApp">
      <WhatsAppIcon /> <span className="nav-t">WhatsApp</span>
      {unseen && <NewBadge size={18} />}
    </NavLink>
  );
}

/* Was a bell in the topbar. It only ever linked here, so the count rides the nav
   item instead of duplicating the destination as a second control. RMs only — the
   count is of calls to THIS person's handset. */
function CallLogNav() {
  const { enabled, user } = useAuth();
  const isRm = enabled && isCallingRm(user?.role);
  // Held in state so opening the page clears the badge immediately rather than
  // after the next poll — the acknowledgement should feel instant.
  const [seenAt, setSeenAt] = useState<string | null>(() => readCallsSeenAt());
  const { data } = useIncomingCalls(seenAt, isRm);
  const unseen = isRm ? (data?.unseen ?? 0) : 0;

  const acknowledge = () => {
    if (!isRm) return;
    // Marked at the newest call we know of, not at "now": a call landing between the
    // last poll and this click would otherwise be silently marked as seen.
    const at = data?.last_incoming_at || new Date().toISOString();
    markCallsSeen(at);
    setSeenAt(at);
  };

  return (
    <NavLink to="/call-log" className={navClass} onClick={acknowledge}
             title={unseen ? `${unseen} incoming call${unseen === 1 ? "" : "s"}` : "Bonvoice Call Log"}>
      <img src="/bonvoice_icon.png" alt="" className="nav-img" />
      <span className="nav-t">Bonvoice Call Log</span>
      {unseen > 0 && <span className="badge">{unseen > 9 ? "9+" : unseen}</span>}
    </NavLink>
  );
}

function UserChip() {
  const { user, devUser, viewAs, loading } = useAuth();
  const switcher = isDevBuild
    ? <DevViewAs current={devUser} onPick={viewAs} busy={!!devUser && loading} />
    : null;

  const init = user ? (user.name || user.email).split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase() : "AD";

  /* Identity only — name and role. Signing out lives on the profile page it links
     to, not here: the rail is navigation, and a destructive action sitting in it
     is one mis-click from ending someone's session mid-shift. */
  return (
    <>
      <NavLink to="/profile" className={({ isActive }) => "user" + (isActive ? " active" : "")} title="Your profile">
        {user?.picture
          ? <img className="av" src={user.picture} alt="" style={{ objectFit: "cover" }} />
          : <div className="av">{init}</div>}
        <div style={{ minWidth: 0 }}>
          <div className="un">{user ? (user.name || user.email) : "Admin"}</div>
          <div className="ur">{user?.role || "Admin"}</div>
        </div>
      </NavLink>
      {switcher}
    </>
  );
}
