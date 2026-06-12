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
