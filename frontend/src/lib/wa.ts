import { useAuth } from "../components/AuthContext";
import { useAppSettings } from "./queries";

/* The WhatsApp 24-hour reply window — the one rule, in one place.

   Gupshup/Meta only let a free-form message through within 24 hours of the customer's
   last INBOUND message; after that only an approved template can reach them. The
   constant was written out separately in WaThread.tsx and Chat.tsx, and the
   notification bell is a third reader — three copies of a boundary that decides
   whether a message can be sent at all is one drift away from the bell promising a
   conversation the composer then refuses.

   Decided on the CLIENT, from `last_inbound_at`, because the boundary moves with the
   clock: a thread crosses from open to closed while the page sits there, and a value
   computed server-side would be right only at the instant of the response. */
export const WA_WINDOW_MS = 24 * 60 * 60 * 1000;

export const waWindowOpen = (lastInboundAt: number | null): boolean =>
  lastInboundAt != null && Date.now() - lastInboundAt < WA_WINDOW_MS;

/* Who may see WhatsApp at all: admins, plus RMs an admin has switched on.

   Shared by the sidebar nav and the notification bell. NOT duplicated: the bell
   lists contact names and phone numbers, so a gate that drifts open here leaks the
   inbox to an RM who cannot open the page it links to. */
export function useWaAllowed(): boolean {
  const { enabled, user } = useAuth();
  const { data: appSettings } = useAppSettings();
  const isAdmin = !enabled || user?.role === "admin";
  const email = (user?.email || "").toLowerCase();
  return isAdmin || !!appSettings?.wa_show_all_rms
    || (!!email && (appSettings?.wa_allowed_emails ?? []).includes(email));
}
