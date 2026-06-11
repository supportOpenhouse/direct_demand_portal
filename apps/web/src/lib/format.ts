/** Display formatting helpers (en-IN). */

function trimNum(x: number): string {
  return String(parseFloat(x.toFixed(2)));
}

/** 85 -> "₹85L" · 150 -> "₹1.5Cr" · null -> "—" */
export function formatLacs(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (n >= 100) return `₹${trimNum(n / 100)}Cr`;
  return `₹${trimNum(n)}L`;
}

/** (70, 90) -> "₹70L – ₹90L" · (70, null) -> "₹70L+" · (null, 90) -> "Up to ₹90L" · (85, 85) -> "₹85L" */
export function budgetLabel(
  min: number | null | undefined,
  max: number | null | undefined,
): string {
  const hasMin = min !== null && min !== undefined;
  const hasMax = max !== null && max !== undefined;
  if (!hasMin && !hasMax) return '—';
  if (hasMin && hasMax) {
    return min === max ? formatLacs(min) : `${formatLacs(min)} – ${formatLacs(max)}`;
  }
  if (hasMin) return `${formatLacs(min)}+`;
  return `Up to ${formatLacs(max)}`;
}

/** ISO string -> "11 Jun 2026" */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** ISO string -> "11 Jun 2026, 5:42 pm" */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  const date = d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  const time = d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true });
  return `${date}, ${time}`;
}

/** "Aarav Mehta" -> "AM" */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  const first = parts[0][0] ?? '';
  const last = parts.length > 1 ? (parts[parts.length - 1][0] ?? '') : '';
  return (first + last).toUpperCase() || '?';
}

/** TatInfo.minutes_left -> "42m left" / "1h 5m left" / "2h 15m over" / "—" */
export function tatLabel(minutesLeft: number | null | undefined): string {
  if (minutesLeft === null || minutesLeft === undefined) return '—';
  const abs = Math.abs(Math.round(minutesLeft));
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  const span = h > 0 ? `${h}h ${m}m` : `${m}m`;
  return minutesLeft < 0 ? `${span} over` : `${span} left`;
}

/** ISO string -> "just now" / "5m ago" / "3h ago" / "2d ago" / "11 Jun 2026" */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (isNaN(t)) return '—';
  const min = Math.floor((Date.now() - t) / 60000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  return formatDate(iso);
}
