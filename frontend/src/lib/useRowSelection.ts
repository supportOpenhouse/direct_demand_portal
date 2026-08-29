import { useMemo, useState } from "react";

/** Row selection by id, scoped to the currently-visible (filtered) ids. */
export function useRowSelection(visibleIds: string[]) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const visibleSet = useMemo(() => new Set(visibleIds), [visibleIds]);
  // only count selections that are still visible under the current filters
  const activeIds = useMemo(() => [...selected].filter((id) => visibleSet.has(id)), [selected, visibleSet]);
  const allChecked = visibleIds.length > 0 && activeIds.length === visibleIds.length;

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const toggleAll = () =>
    setSelected((s) => {
      const n = new Set(s);
      if (allChecked) visibleIds.forEach((id) => n.delete(id));
      else visibleIds.forEach((id) => n.add(id));
      return n;
    });

  const clear = () => setSelected(new Set());

  /* First N in the order they're rendered — visibleIds is already filtered and sorted
     by the page, which `selected` is not (it's a Set, so insertion order). REPLACES
     the selection rather than adding to it: "first 10" has to mean ten, not ten more.
     Fewer than N rows on screen selects all of them. */
  const selectFirst = (n: number) => setSelected(new Set(visibleIds.slice(0, n)));

  return { selected, activeIds, count: activeIds.length, visibleCount: visibleIds.length,
           allChecked, toggle, toggleAll, clear, selectFirst,
           has: (id: string) => selected.has(id) };
}
