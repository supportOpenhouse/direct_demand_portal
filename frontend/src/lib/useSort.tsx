/* Reusable click-to-sort for any table. Pages declare per-column accessors;
   <SortTh> renders a clickable header with a direction caret. Nulls sort last. */
import { useMemo, useState } from "react";

type Dir = "asc" | "desc";
type Accessor<T> = (item: T) => string | number | null | undefined;

export function useSort<T>(items: T[], accessors: Record<string, Accessor<T>>, initialKey?: string, initialDir: Dir = "asc") {
  const [key, setKey] = useState<string | null>(initialKey ?? null);
  const [dir, setDir] = useState<Dir>(initialDir);

  const sorted = useMemo(() => {
    if (!key || !accessors[key]) return items;
    const acc = accessors[key];
    const factor = dir === "asc" ? 1 : -1;
    return [...items].sort((a, b) => {
      const va = acc(a);
      const vb = acc(b);
      const na = va === null || va === undefined || va === "";
      const nb = vb === null || vb === undefined || vb === "";
      if (na && nb) return 0;
      if (na) return 1; // nulls always last, regardless of direction
      if (nb) return -1;
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * factor;
      return String(va).localeCompare(String(vb), undefined, { numeric: true }) * factor;
    });
  }, [items, key, dir, accessors]);

  const onSort = (k: string) => {
    if (key === k) setDir(dir === "asc" ? "desc" : "asc");
    else {
      setKey(k);
      setDir("asc");
    }
  };

  return { sorted, sortKey: key, dir, onSort };
}

export function SortTh({
  label,
  sortKey,
  activeKey,
  dir,
  onSort,
  style,
  align = "left",
}: {
  label: string;
  sortKey: string;
  activeKey: string | null;
  dir: Dir;
  onSort: (k: string) => void;
  style?: React.CSSProperties;
  align?: "left" | "right" | "center";
}) {
  const active = activeKey === sortKey;
  return (
    <th
      onClick={() => onSort(sortKey)}
      style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap", textAlign: align, ...style }}
      title="Click to sort"
    >
      {label}
      <span style={{ marginLeft: 5, opacity: active ? 1 : 0.25, fontSize: 9 }}>
        {active ? (dir === "asc" ? "▲" : "▼") : "▲▼"}
      </span>
    </th>
  );
}
