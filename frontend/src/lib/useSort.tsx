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
    const [nk, nd] = nextSort(key, dir, k, initialKey ?? null, initialDir);
    setKey(nk);
    setDir(nd);
  };

  return { sorted, sortKey: key, dir, onSort };
}

/* asc → desc → back to the default — the one cycle every sortable header follows. */
function nextSort(key: string | null, dir: Dir, k: string, initialKey: string | null, initialDir: Dir): [string | null, Dir] {
  if (key !== k) return [k, "asc"];
  if (dir === "asc") return [k, "desc"];
  return [initialKey, initialDir];
}

/* For a table the SERVER pages (Call Log, Dialer history, Huvo calls, Activity Logs): the
   browser holds one page, so sorting it here would reorder only what's on screen. This keeps
   the same header cycle and hands back `params` ({sort, dir}) for the query; the server's
   whitelist (backend/app/core/sorting.py) does the ordering. `onChange` runs on every click —
   pages pass their "back to page 1". */
export function useServerSort(onChange?: () => void) {
  const [key, setKey] = useState<string | null>(null);
  const [dir, setDir] = useState<Dir>("asc");
  const onSort = (k: string) => {
    const [nk, nd] = nextSort(key, dir, k, null, "asc");
    setKey(nk);
    setDir(nd);
    onChange?.();
  };
  return { sortKey: key, dir, onSort, params: key ? { sort: key, dir } : {} };
}

export function SortTh({
  label,
  sortKey,
  activeKey,
  dir,
  onSort,
  style,
  align = "left",
  className,
  hint,
}: {
  label: string;
  sortKey: string;
  activeKey: string | null;
  dir: Dir;
  onSort: (k: string) => void;
  style?: React.CSSProperties;
  align?: "left" | "right" | "center";
  className?: string;
  /** what the column means — shown before the sort action in the tooltip */
  hint?: string;
}) {
  const active = activeKey === sortKey;
  const action = !active ? "Sort ascending" : dir === "asc" ? "Sort descending" : "Back to default order";
  return (
    <th
      className={className}
      onClick={() => onSort(sortKey)}
      style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap", textAlign: align, ...style }}
      title={hint ? `${hint} — ${action.toLowerCase()}` : action}
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
