/* Compact filter controls styled with the prototype's field/select look. */

/** An option is either a bare string (value === label) or a {value, label} pair
    when the displayed text differs from the stored value (e.g. "Meta" → "meta"). */
export type FilterOption = string | { value: string; label: string };

export function FilterSelect({
  label,
  value,
  options,
  onChange,
  width = 170,
}: {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (v: string) => void;
  width?: number;
}) {
  const opts = options.map((o) => (typeof o === "string" ? { value: o, label: o } : o));
  return (
    <div className="field" style={{ marginBottom: 0, width }}>
      <select value={value} onChange={(e) => onChange(e.target.value)} style={{ padding: "7px 10px", fontSize: 12.5 }}>
        <option value="">{label}: All</option>
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/** unique non-empty values of a field, sorted, for building filter options */
export function uniqueValues<T>(items: T[], get: (item: T) => string | null | undefined): string[] {
  return Array.from(new Set(items.map(get).filter((v): v is string => !!v && !!v.trim()))).sort();
}

/** Budget range filter — two ₹ Lakh inputs (values stored as lakh strings). The
    leading label says what the range is for (defaults to "Price"). */
export function BudgetRange({ min, max, onMin, onMax, label = "Price" }: {
  min: string; max: string; onMin: (v: string) => void; onMax: (v: string) => void; label?: string;
}) {
  const box = { padding: "8px 10px", fontSize: 13, width: 80 } as const;
  return (
    <div className="field" style={{ marginBottom: 0, display: "flex", gap: 6, alignItems: "center" }}>
      <span style={{ color: "var(--muted)", fontSize: 12, fontWeight: 600 }}>{label}</span>
      <input type="number" min={0} step="5" placeholder="min" value={min} onChange={(e) => onMin(e.target.value)} style={box} title={`Min ${label.toLowerCase()} (₹ Lakhs)`} />
      <span style={{ color: "var(--muted)", fontSize: 12 }}>–</span>
      <input type="number" min={0} step="5" placeholder="max" value={max} onChange={(e) => onMax(e.target.value)} style={box} title={`Max ${label.toLowerCase()} (₹ Lakhs)`} />
      <span style={{ color: "var(--muted)", fontSize: 11, fontWeight: 600 }}>₹ L</span>
    </div>
  );
}

/** Date presets for the received-at filter. "" = All (no constraint). */
export type DatePreset = "" | "today" | "yesterday" | "week" | "month" | "custom";

export const DATE_PRESETS: { value: Exclude<DatePreset, "">; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
  { value: "custom", label: "Custom range" },
];

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

/** True if `iso` falls within the chosen preset (or [from, to] when custom).
    Comparison is day-granular and inclusive of both ends of a custom range. */
export function inDatePreset(iso: string | null, preset: DatePreset, from: string, to: string): boolean {
  if (!preset) return true;
  if (!iso) return false;
  const day = startOfDay(new Date(iso)).getTime();
  const now = new Date();
  const today = startOfDay(now).getTime();
  if (preset === "today") return day === today;
  if (preset === "yesterday") return day === today - 86_400_000;
  if (preset === "week") {
    const s = startOfDay(now);
    s.setDate(s.getDate() - ((s.getDay() + 6) % 7)); // back to Monday
    return day >= s.getTime();
  }
  if (preset === "month") return new Date(iso).getMonth() === now.getMonth() && new Date(iso).getFullYear() === now.getFullYear();
  if (preset === "custom") {
    const lo = from ? startOfDay(new Date(from)).getTime() : null;
    const hi = to ? startOfDay(new Date(to)).getTime() : null;
    if (lo != null && day < lo) return false;
    if (hi != null && day > hi) return false;
    return true;
  }
  return true;
}

/** Date filter: a preset select that reveals two date inputs when "Custom range" is picked. */
export function DateFilter({ preset, from, to, onPreset, onFrom, onTo }: {
  preset: DatePreset; from: string; to: string;
  onPreset: (v: DatePreset) => void; onFrom: (v: string) => void; onTo: (v: string) => void;
}) {
  const box = { padding: "7px 10px", fontSize: 12.5 } as const;
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <FilterSelect label="Date" value={preset} options={DATE_PRESETS} onChange={(v) => onPreset(v as DatePreset)} width={140} />
      {preset === "custom" && (
        <div className="field" style={{ marginBottom: 0, display: "flex", gap: 6, alignItems: "center" }}>
          <input type="date" value={from} onChange={(e) => onFrom(e.target.value)} style={box} title="From date" />
          <span style={{ color: "var(--muted)", fontSize: 12 }}>–</span>
          <input type="date" value={to} onChange={(e) => onTo(e.target.value)} style={box} title="To date" />
        </div>
      )}
    </div>
  );
}

/** price_lacs (lakhs) within a [minLac, maxLac] range; items without a price drop
    out once any bound is set. Empty bounds = no constraint. */
export function inBudget(priceLacs: number | null | undefined, minLac: string, maxLac: string): boolean {
  const lo = minLac.trim() ? parseFloat(minLac) : null;
  const hi = maxLac.trim() ? parseFloat(maxLac) : null;
  if (lo == null && hi == null) return true;
  if (priceLacs == null) return false;
  if (lo != null && priceLacs < lo) return false;
  if (hi != null && priceLacs > hi) return false;
  return true;
}
