/* 1:1 port of the prototype's .topbar. Reminders / Add New Lead are later-phase. */
import { Link, useLocation } from "react-router-dom";
import { IconBell, IconPlusBold, WhatsAppIcon } from "./icons";
import { useToast } from "./Toast";
import { useAuth } from "./AuthContext";
import { useMyCalls, useWaLatest } from "../lib/queries";
import { isCallingRm } from "../lib/roles";
import { readWaSeenAt } from "../lib/whatsapp";
import GlobalSearch from "./GlobalSearch";

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/leads/new": "New Leads",
  "/leads/call-not-received": "Call Not Received",
  "/leads/followup": "Follow Up",
  "/leads/qualified": "Qualified Leads",
  "/leads/pipeline": "Pipeline Leads",
  "/leads/converted": "Converted Leads",
  "/leads/rejected": "Rejected Leads",
  "/reminders": "Reminders",
  "/inventory": "Live Inventory",
  "/supply": "Supply Pipeline",
  "/societies": "Society Insights",
  "/goldmine": "Gold Mine — Re-engagement",
  "/dialer/schedule": "Schedule Campaign",
  "/dialer/previous": "Previous Campaigns",
  "/settings": "Settings & Access",
  "/logs": "Activity Logs",
  "/call-log": "Bonvoice Call Log",
  "/huvo-calls": "Huvo Call Log",
  "/chat": "WhatsApp",
  "/live-calls": "Live Calls",
};

/* Handset with signal arcs — this RM's own phone ringing, as opposed to the outbound
   arrow on the admin Auto Dialer icon. */
const IconLiveCall = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
    <path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91" />
    <path d="M15.5 5.5a5 5 0 0 1 3 3" /><path d="M14.5 2a8.5 8.5 0 0 1 5.5 5.5" />
  </svg>
);

/* RMs only. Admins run campaigns, they don't take the calls, so the button would be
   permanently dead chrome for them. Note the consequence: an admin who IS in a
   campaign's RM pool gets rung with no way to reach this page or mark the result. */
function LiveCallsButton() {
  // `!enabled` keeps the gate biting while impersonating, matching Sidebar.tsx.
  // test_rm counts: a test RM takes real calls and has to mark the results.
  const { enabled, user } = useAuth();
  const isRm = enabled && isCallingRm(user?.role);
  // Hook order can't depend on a condition, so always call it and gate on `enabled`.
  const { data } = useMyCalls(true, isRm);  // the page owns polling; this reads cache

  if (!isRm) return null;

  const live = !!data?.now_calling;
  const queued = data?.upcoming?.length || 0;
  const unmarked = (data?.completed || []).filter((c) => !c.call_result).length;

  return (
    <Link
      className={"btn lc-btn" + (live ? " live" : queued ? " queued" : "")}
      to="/live-calls"
      title={live ? "You are on a call now" : queued ? `${queued} calls incoming` : "Live Calls"}
    >
      <IconLiveCall /> Live Calls
      {/* Unmarked results are the only thing that nags — the page never interrupts */}
      {unmarked > 0 && <span className="lc-btn-count">{unmarked}</span>}
    </Link>
  );
}

export default function Topbar() {
  const { pathname } = useLocation();
  const toast = useToast();

  // "Unseen" = an inbound message newer than the last time this browser opened the
  // WhatsApp page. Per-browser via localStorage rather than a read-receipt table —
  // one person watching the inbox is the actual use case here.
  const { data: latest } = useWaLatest(true);
  const seenAt = readWaSeenAt();
  const unseen = !!latest?.last_inbound_at && +new Date(latest.last_inbound_at) > seenAt
    && pathname !== "/chat";
  const title =
    TITLES[pathname] ||
    (/^\/leads\/[^/]+$/.test(pathname) ? "Lead Details" : "Dashboard");

  return (
    <div className="topbar">
      <h1 id="page-title">{title}</h1>
      <GlobalSearch />
      <button className="btn orange" onClick={() => toast("Reminders arrive in a later phase", "gold", "⏰")}>
        <IconBell /> Reminders
      </button>
      <button className="btn green" onClick={() => toast("Lead capture arrives in a later phase", "blue", "＋")}>
        <IconPlusBold /> Add New Lead
      </button>
      <LiveCallsButton />
      {/* RMs see their assigned conversations; the API scopes what comes back */}
      <Link className="btn wa" to="/chat" style={{ position: "relative" }}>
        <WhatsAppIcon /> WhatsApp
        {unseen && (
          <span
            title="New messages"
            style={{
              position: "absolute", top: -3, right: -3, width: 10, height: 10,
              borderRadius: "50%", background: "#f97316", border: "2px solid var(--panel)",
            }}
          />
        )}
      </Link>
    </div>
  );
}
