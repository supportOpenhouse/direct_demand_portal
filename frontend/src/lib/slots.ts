/* Book-Visits time-slot logic — six fixed 2-hour slots, next-7-day date options,
   and today's "1 hour into the slot" cutoff. Pure client-side wall-clock logic
   (no API): a slot disables when now ≥ slotStartHour + 1h, but only for today. */

export interface Slot {
  label: string; // verbatim value sent as selected_time
  startHour: number; // 24h
}

export const SLOTS: Slot[] = [
  { label: "9-11 AM", startHour: 9 },
  { label: "11-1 PM", startHour: 11 },
  { label: "1-3 PM", startHour: 13 },
  { label: "3-5 PM", startHour: 15 },
  { label: "5-7 PM", startHour: 17 },
  { label: "7-9 PM", startHour: 19 },
];

export interface DayOption {
  date: string; // YYYY-MM-DD (local wall-clock)
  dow: string; // Mon, Tue…
  dayNum: string;
  month: string;
  isToday: boolean;
}

function toYMD(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Today → +6 (seven options). */
export function next7Days(now = new Date()): DayOption[] {
  const out: DayOption[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(now);
    d.setDate(now.getDate() + i);
    out.push({
      date: toYMD(d),
      dow: d.toLocaleDateString("en-IN", { weekday: "short" }),
      dayNum: String(d.getDate()),
      month: d.toLocaleDateString("en-IN", { month: "short" }),
      isToday: i === 0,
    });
  }
  return out;
}

/** A slot is disabled only on today, once we're 1h into it. Future dates: all open. */
export function isSlotDisabled(dateYMD: string, startHour: number, now = new Date()): boolean {
  if (dateYMD !== toYMD(now)) return false;
  const nowHours = now.getHours() + now.getMinutes() / 60;
  return nowHours >= startHour + 1;
}

/** Mask a partial mobile (last 5–10 digits) for display. */
export function maskMobile(digits: string): string {
  const d = digits.replace(/\D/g, "");
  if (!d) return "—";
  return "••• " + d;
}
