/* Real WhatsApp deep links. Opens wa.me in a new tab. */

function digits(phone: string | null): string {
  const d = (phone || "").replace(/\D/g, "");
  if (d.length === 10) return "91" + d; // bare Indian mobile → add country code
  return d;
}

/** Open a chat with a specific number (optionally prefilled). */
export function waChat(phone: string | null, text?: string) {
  const n = digits(phone);
  if (!n) return;
  const url = `https://wa.me/${n}${text ? "?text=" + encodeURIComponent(text) : ""}`;
  window.open(url, "_blank", "noopener");
}

/* When this browser last had the WhatsApp inbox open. Drives the topbar's unseen dot.
   Deliberately local, not a server-side read receipt — the inbox has one watcher. */
const WA_SEEN_KEY = "dd_wa_seen_at";
export const readWaSeenAt = (): number => Number(localStorage.getItem(WA_SEEN_KEY) || 0);
export const markWaSeen = () => localStorage.setItem(WA_SEEN_KEY, String(Date.now()));

/** Open WhatsApp with a prefilled message and no recipient (user picks the contact). */
export function waShare(text: string) {
  window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener");
}
