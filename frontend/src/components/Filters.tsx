/* Compact filter controls styled with the prototype's field/select look. */

export function FilterSelect({
  label,
  value,
  options,
  onChange,
  width = 170,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  width?: number;
}) {
  return (
    <div className="field" style={{ marginBottom: 0, width }}>
      <select value={value} onChange={(e) => onChange(e.target.value)} style={{ padding: "7px 10px", fontSize: 12.5 }}>
        <option value="">{label}: All</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
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

/** Budget range filter — two compact ₹ Cr inputs (values stored as Cr strings). */
export function BudgetRange({ min, max, onMin, onMax }: {
  min: string; max: string; onMin: (v: string) => void; onMax: (v: string) => void;
}) {
  const box = { padding: "7px 8px", fontSize: 12.5, width: 64 } as const;
  return (
    <div className="field" style={{ marginBottom: 0, display: "flex", gap: 5, alignItems: "center" }}>
      <input type="number" min={0} step="0.05" placeholder="min" value={min} onChange={(e) => onMin(e.target.value)} style={box} title="Min budget (₹ Cr)" />
      <span style={{ color: "var(--muted)", fontSize: 12 }}>–</span>
      <input type="number" min={0} step="0.05" placeholder="max" value={max} onChange={(e) => onMax(e.target.value)} style={box} title="Max budget (₹ Cr)" />
      <span style={{ color: "var(--muted)", fontSize: 11, fontWeight: 600 }}>₹ Cr</span>
    </div>
  );
}

/** price_lacs (lakhs) within a [minCr, maxCr] range; items without a price drop out
    once any bound is set. Empty bounds = no constraint. */
export function inBudget(priceLacs: number | null | undefined, minCr: string, maxCr: string): boolean {
  const lo = minCr.trim() ? parseFloat(minCr) * 100 : null;
  const hi = maxCr.trim() ? parseFloat(maxCr) * 100 : null;
  if (lo == null && hi == null) return true;
  if (priceLacs == null) return false;
  if (lo != null && priceLacs < lo) return false;
  if (hi != null && priceLacs > hi) return false;
  return true;
}
