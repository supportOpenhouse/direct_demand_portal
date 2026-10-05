import { useSearchParams } from "react-router-dom";
import { useAuth } from "../components/AuthContext";
import SlideTabs from "../components/SlideTabs";
import CampaignsTab from "../features/waCampaigns/CampaignsTab";
import AutoTab from "../features/waCampaigns/AutoTab";
import TemplatesTab from "../features/waCampaigns/TemplatesTab";

/* WhatsApp Campaigns — templates and SENDING (spec §9). Responses live on /chat.

   Admin only: every endpoint behind these tabs is `require_admin`, and the nav link is
   admin-gated — this is the third layer, so a pasted /wa-campaigns link shows "Admins only"
   rather than a Templates tab whose every call 403s into an empty-looking list.

   The tab is in `?tab=` so other pages can deep-link to it. TABS runs in the spec's order —
   Campaigns, Auto campaigns, Templates — so Campaigns is where the page lands, and an unknown
   `?tab=` falls back to the first. `?tab=auto&seed=<campaignId>` (the campaign page's "Make it automatic")
   opens the Auto tab's form prefilled from that campaign. */
const TABS = [
  { key: "campaigns", label: "Campaigns", el: <CampaignsTab /> },
  { key: "auto", label: "Auto campaigns", el: <AutoTab /> },
  { key: "templates", label: "Templates", el: <TemplatesTab /> },
];

export default function WaCampaigns() {
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((t) => t.key === params.get("tab")) ?? TABS[0];

  if (!isAdmin) {
    return (
      <div className="card">
        <div className="empty" style={{ padding: 48, textAlign: "center" }}>
          <div style={{ fontWeight: 600, color: "var(--ink-2)" }}>Admins only</div>
          <div style={{ fontSize: 12.5, marginTop: 6 }}>
            WhatsApp campaigns message real customers, so building and sending them is limited to admins.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="wc-head">
        <SlideTabs className="view-toggle">
          {TABS.map((t) => (
            <button key={t.key} className={t.key === tab.key ? "on" : ""}
              onClick={() => setParams({ tab: t.key })}>{t.label}</button>))}
        </SlideTabs>
      </div>
      {tab.el}
    </div>
  );
}
