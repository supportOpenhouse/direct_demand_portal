/* 1:1 port of the prototype's .topbar. Reminders / Add New Lead are later-phase. */
import { useLocation } from "react-router-dom";
import { IconSearch, IconBell, IconPlusBold } from "./icons";
import { useToast } from "./Toast";
import { useSearch } from "./SearchContext";

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/leads/new": "New Leads",
  "/leads/qualified": "Qualified Leads",
  "/leads/pipeline": "Pipeline Leads",
  "/leads/converted": "Converted Leads",
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
  const { query, setQuery } = useSearch();
  const title =
    TITLES[pathname] ||
    (/^\/leads\/[^/]+$/.test(pathname) ? "Lead Details" : "Dashboard");

  return (
    <div className="topbar">
      <h1 id="page-title">{title}</h1>
      <div className="search">
        <IconSearch />
        <input
          placeholder="Search property, society…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <button className="btn orange" onClick={() => toast("Reminders arrive in a later phase", "gold", "⏰")}>
        <IconBell /> Reminders
      </button>
      <button className="btn green" onClick={() => toast("Lead capture arrives in a later phase", "blue", "＋")}>
        <IconPlusBold /> Add New Lead
      </button>
    </div>
  );
}
