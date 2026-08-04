/* 1:1 port of the prototype's .topbar. Reminders / Add New Lead are later-phase. */
import { Link, useLocation } from "react-router-dom";
import { IconBell, IconPlusBold, WhatsAppIcon } from "./icons";
import { useToast } from "./Toast";
import { useWaLatest } from "../lib/queries";
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
  "/chat": "WhatsApp",
};

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
