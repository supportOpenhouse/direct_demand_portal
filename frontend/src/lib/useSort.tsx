/* Reusable click-to-sort for any table. Pages declare per-column accessors;
   <SortTh> renders a clickable header with a direction caret. Nulls sort last. */
import { useMemo, useState } from "react";
import { IconChevronDown, IconChevronUp, IconChevronsUpDown } from "../components/icons";

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

  /* Three clicks, then back where you started: asc → desc → the page's own order.
     Two-state (asc ⇄ desc forever) left no way back to the default ordering — New
     Leads' NEW-first grouping or Follow-up's due-date ranking — short of reloading.
     "Default" is the initial key if the page gave one, otherwise no sort at all, which
     hands `items` through untouched in whatever order the page built them. */
  const onSort = (k: string) => {
    if (key !== k) {
      setKey(k);
      setDir("asc");
    } else if (dir === "asc") {
      setDir("desc");
    } else {
      setKey(initialKey ?? null);
      setDir(initialDir);
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
      title={!active ? "Sort ascending" : dir === "asc" ? "Sort descending" : "Back to default order"}
    >
      {label}
      {/* Was fontSize 9 + opacity .25: icons size to 1em, so that drew a 9px chevron at a
          quarter strength on already-muted header text — present, but invisible.
          Unsorted columns show the two-way "sortable" mark; the sorted one shows which way. */}
      <span className={`sort-ind${active ? " on" : ""}`} aria-hidden>
        {active ? (dir === "asc" ? <IconChevronUp /> : <IconChevronDown />) : <IconChevronsUpDown />}
      </span>
    </th>
  );
}
