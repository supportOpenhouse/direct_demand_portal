/* 1:1 port of the prototype's .topbar.

   Reminders and Add New Lead used to sit here. Both only ever raised a toast saying
   the feature was coming, so they were two permanently disabled controls taking the
   most valuable space on every page — removed rather than left as furniture.
   "Add lead" came back (15 Sep) as a working control: components/AddLead.tsx. */
import { useLocation } from "react-router-dom";
import { NotificationBell } from "./NotificationBell";
import { AddLeadButton } from "./AddLead";

const TITLES: Record<string, string> = {
  "/": "Home",
  "/leads/new": "New Leads",
  "/leads/call-not-received": "Call Not Received",
  "/leads/followup": "Call Back Again",
  "/leads/qualified": "Qualified Leads (Requirement Captured)",
  "/leads/pipeline": "Visited Leads",
  "/leads/revisit": "Pipeline Leads",
  "/leads/converted": "Converted Leads",
  "/leads/rejected": "Rejected Leads",
  "/reminders": "Reminders",
  "/inventory": "Live Inventory",
  "/supply": "Supply Pipeline",
  "/societies": "Society Insights",
  "/goldmine": "Gold Mine — Re-engagement",
  "/dialer/schedule": "Schedule Campaign",
  "/dialer/previous": "Previous Campaigns",
  "/profile": "Your Profile",
  "/settings": "Settings & Access",
  "/logs": "Activity Logs",
  "/reports": "Reports",
  "/reports/detail": "RM Report",
  "/call-log": "Bonvoice Call Log",
  "/huvo-calls": "Huvo Call Log",
  "/chat": "WhatsApp",
  "/meta-leads": "Meta Leads",
  "/live-calls": "Live Calls",
};

export default function Topbar() {
  const { pathname } = useLocation();
  const title =
    TITLES[pathname] ||
    (/^\/leads\/[^/]+$/.test(pathname) ? "Lead Details" : "Home");
  // a "(…)" tail on a title is a clarifier, not part of the name — render it lighter
  const paren = title.indexOf(" (");

  return (
    <div className="topbar">
      <h1 id="page-title">
        {paren === -1 ? title : (
          <>
            {title.slice(0, paren)}
            <span style={{ fontWeight: 500, fontSize: "0.62em", color: "var(--muted)", marginLeft: 7, letterSpacing: 0 }}>
              {title.slice(paren + 1)}
            </span>
          </>
        )}
      </h1>
      <span style={{ flex: 1 }} />
      {/* Pages portal their own actions here (Select, Download CSV) — the strip is
          the page's action bar, so a page-specific button belongs in it rather than
          duplicated into every toolbar. */}
      <div id="topbar-slot" />
      {/* on every page, unlike the slot's page actions — a buyer can call in anywhere */}
      <AddLeadButton />
      <NotificationBell />
    </div>
  );
}
