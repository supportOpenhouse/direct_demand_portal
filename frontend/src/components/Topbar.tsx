/* 1:1 port of the prototype's .topbar. Reminders / Add New Lead are later-phase. */
import { useLocation } from "react-router-dom";
import { IconBell, IconPlusBold } from "./icons";
import { useToast } from "./Toast";
import GlobalSearch from "./GlobalSearch";

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/leads/new": "New Leads",
  "/leads/followup": "Follow-up",
  "/leads/qualified": "Qualified Leads",
  "/leads/pipeline": "Pipeline Leads",
  "/leads/converted": "Converted Leads",
  "/leads/rnr": "RNR — Ring No Response",
  "/leads/rejected": "Rejected Leads",
  "/reminders": "Reminders",
  "/inventory": "Live Inventory",
  "/supply": "Supply Pipeline",
  "/societies": "Society Insights",
  "/goldmine": "Gold Mine — Re-engagement",
  "/settings": "Settings & Access",
  "/logs": "Activity Logs",
};

export default function Topbar() {
  const { pathname } = useLocation();
  const toast = useToast();
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
    </div>
  );
}
