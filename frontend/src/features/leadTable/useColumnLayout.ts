/* Which columns a lead page shows, and in what order — per page, in this browser.

   Stored as the ordered list of VISIBLE column ids under `dd_cols:<page>`. Anything not
   in the list is hidden, so there is one source of truth for both "shown" and "order".

   A saved layout is filtered against the registry on read: a column renamed or removed
   in code must not leave a dead id that renders an empty <th>, and a layout that ends up
   with nothing left falls back to the page default rather than an empty table. */
import { useCallback, useState } from "react";
import { COLUMN_BY_ID } from "./columns";

const key = (page: string) => `dd_cols:${page}`;

/* Which columns exist is passed in, so a non-lead table (Demand Dashboard) can use the
   same storage, the same stale-id filtering and the same modal. */
type Registry = Record<string, unknown>;

function read(page: string, defaults: string[], byId: Registry): string[] {
  try {
    const raw = localStorage.getItem(key(page));
    if (!raw) return defaults;
    const ids = (JSON.parse(raw) as unknown[]).filter(
      (id): id is string => typeof id === "string" && id in byId,
    );
    return ids.length ? [...new Set(ids)] : defaults;
  } catch {
    // private mode, or a hand-edited value that isn't JSON — use the page's own layout
    return defaults;
  }
}

export function useColumnLayout(page: string, defaults: string[], byId: Registry = COLUMN_BY_ID) {
  const [cols, setColsState] = useState<string[]>(() => read(page, defaults, byId));

  const setCols = useCallback((next: string[]) => {
    setColsState(next);
    try { localStorage.setItem(key(page), JSON.stringify(next)); } catch { /* applied, not saved */ }
  }, [page]);

  const reset = useCallback(() => {
    setColsState(defaults);
    try { localStorage.removeItem(key(page)); } catch { /* nothing saved to clear */ }
    // defaults is a per-page constant; listing it would re-create reset every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const isDefault = cols.length === defaults.length && cols.every((c, i) => c === defaults[i]);

  return { cols, setCols, reset, isDefault, defaults };
}
