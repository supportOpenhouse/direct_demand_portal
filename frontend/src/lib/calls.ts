/* When this browser last acknowledged incoming calls.

   Per-browser via localStorage rather than a column on call_logs, exactly like the
   WhatsApp bell (lib/whatsapp.ts). A flag on the row would be wrong here: two RMs can
   both be involved in a call, and one clearing their bell must not clear the other's.

   Stored as an ISO string so it can be handed straight to the API as `since`. */
const KEY = "dd_calls_seen_at";

export const readCallsSeenAt = (): string | null => localStorage.getItem(KEY);

export const markCallsSeen = (at?: string | null) =>
  localStorage.setItem(KEY, at || new Date().toISOString());
