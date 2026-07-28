/* WhatsApp conversation for one lead, on the lead-detail page.

   Admin-only, matching the WhatsApp page — renders nothing at all for other roles
   rather than a permission error, since the API would refuse them anyway. */
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useWaMessages } from "../lib/queries";
import { useAuth } from "./AuthContext";
import { WhatsAppIcon } from "./icons";
import WaThread from "./WaThread";

export default function WaLeadCard({ phone }: { phone: string | null }) {
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  const { data, isLoading } = useWaMessages(isAdmin && phone ? phone : undefined);

  // server sends newest first; the thread reads oldest first
  const messages = useMemo(() => [...(data?.items ?? [])].reverse(), [data]);
  const lastInboundAt = useMemo(() => {
    const times = messages.filter((m) => m.direction === "in").map((m) => +new Date(m.created_at));
    return times.length ? Math.max(...times) : null;
  }, [messages]);

  if (!isAdmin || !phone) return null;

  // the number this lead is actually reachable on, in the form Gupshup addresses
  const waPhone = messages[0]?.phone ?? phone.replace(/\D/g, "").slice(-10);

  return (
    <div className="card" style={{ padding: 14, display: "flex", flexDirection: "column" }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        borderBottom: "1px solid var(--line)", paddingBottom: 9, marginBottom: 11,
      }}>
        <span style={{ width: 16, height: 16, color: "#25b15a", display: "inline-flex" }}>
          <WhatsAppIcon />
        </span>
        <b style={{ fontSize: 14 }}>WhatsApp</b>
        <Link to="/chat" className="btn ghost sm" style={{ marginLeft: "auto" }}>All chats</Link>
      </div>

      {isLoading ? (
        <div className="empty" style={{ padding: 20 }}>Loading…</div>
      ) : messages.length === 0 ? (
        <div className="empty" style={{ padding: 20, fontSize: 12.5, lineHeight: 1.6 }}>
          No WhatsApp messages from this number yet. They have to message your business
          number first — WhatsApp doesn’t let a business open a conversation with
          free-form text.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", maxHeight: 420 }}>
          <WaThread
            phone={waPhone}
            messages={messages}
            lastInboundAt={lastInboundAt}
            sendEnabled={data?.send_enabled ?? false}
          />
        </div>
      )}
    </div>
  );
}
