import { useEffect, useState } from "react";
import { IconRefresh } from "./icons";
import { SelectFirst } from "./SelectFirst";

/* [Select] [Select first…] "Showing 1-50 of N" … [Rows 50▾] Prev / Page [n] / N / Next.

   Ported from Direct Inventory's filtered-header. Theirs pages the SERVER; these
   tables are already fully in the client, so this only slices an array -- but the
   control reads the same, which is the point.

   Select moved here from the topbar (16 Sep). It acts on the rows this bar describes,
   so it belongs beside "Showing 1–50 of N" rather than in a strip that also carries
   Download CSV — and the page size and the select size now sit in the same row, which
   is where you're looking when you decide how many to take. */
export const PAGE_SIZE = 50;
export const PAGE_SIZES = [50, 100, 200, 500] as const;
/** "Show all rows on one page." A sentinel rather than Infinity: page * Infinity is NaN
    on page 0, which would slice nothing. */
export const ALL_ROWS = "all" as const;
export type PageSize = number | typeof ALL_ROWS;

/* One remembered size for every lead table. Someone who works 500 rows at a time wants
   500 on the next page they open too, not a reset to 50 on every navigation. Browser
   storage can be missing (private mode) — then it just starts at 50. */
const SIZE_KEY = "dd_page_size";
function readSize(): PageSize {
  try {
    const v = localStorage.getItem(SIZE_KEY);
    if (v === ALL_ROWS) return ALL_ROWS;
    const n = Number(v);
    return (PAGE_SIZES as readonly number[]).includes(n) ? n : PAGE_SIZE;
  } catch {
    return PAGE_SIZE;
  }
}

export function usePaging<T>(rows: T[]) {
  const [page, setPage] = useState(0);
  const [sizeChoice, setSizeChoice] = useState<PageSize>(readSize);
  // "All" is one page holding every row; max(1) keeps an empty list from dividing by 0
  const size = sizeChoice === ALL_ROWS ? Math.max(1, rows.length) : sizeChoice;
  const pages = Math.max(1, Math.ceil(rows.length / size));
  // A filter that shrinks the list can strand you past the end, showing an empty
  // table with rows plainly available behind it.
  useEffect(() => { setPage((p) => Math.min(p, pages - 1)); }, [pages]);

  const setSize = (s: PageSize) => {
    setSizeChoice(s);
    // back to the top: page 7 of 50-per-page is a different set of rows at 200-per-page
    setPage(0);
    try { localStorage.setItem(SIZE_KEY, String(s)); } catch { /* not persisted, still applied */ }
  };

  return { page, setPage, pages, size, sizeChoice, setSize,
           slice: rows.slice(page * size, page * size + size) };
}

export interface PagerSelect {
  on: boolean;
  onToggle: () => void;
  /** rows passing the current filters — what "Select first N" counts from */
  total: number;
  onPick: (n: number) => void;
}

export function Pager({
  page, pages, size, total, onPage, onReload, sizeChoice, onSize, select,
}: {
  page: number; pages: number; size: number; total: number;
  onPage: (p: number) => void;
  onReload?: () => void;
  /** omit both to hide the rows-per-page control */
  sizeChoice?: PageSize;
  onSize?: (s: PageSize) => void;
  /** omit on tables with no bulk actions */
  select?: PagerSelect;
}) {
  const [box, setBox] = useState(String(page + 1));
  useEffect(() => { setBox(String(page + 1)); }, [page]);

  const go = () => {
    const n = parseInt(box, 10);
    onPage(Number.isFinite(n) ? Math.min(pages, Math.max(1, n)) - 1 : page);
  };

  const first = total === 0 ? 0 : page * size + 1;
  const last = Math.min(total, page * size + size);

  return (
    <div className="pager">
      {select && (
        <span className="pager-select">
          <button className={"btn sm" + (select.on ? "" : " ghost")} onClick={select.onToggle}>
            {select.on ? "Exit Select" : "Select"}
          </button>
          {/* the shortcut only means anything once rows can be picked */}
          {select.on && <SelectFirst total={select.total} onPick={select.onPick} />}
        </span>
      )}
      <span className="muted">Showing {first}–{last} of {total.toLocaleString("en-IN")}</span>
      <span className="pager-spacer" />
      {onSize && (
        <label className="pager-size">
          <span className="page-of">Rows</span>
          <select
            className="ctl"
            aria-label="Rows per page"
            value={String(sizeChoice ?? size)}
            onChange={(e) => onSize(e.target.value === ALL_ROWS ? ALL_ROWS : Number(e.target.value))}
          >
            {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
            <option value={ALL_ROWS}>All</option>
          </select>
        </label>
      )}
      <button className="btn ghost sm" disabled={page === 0} onClick={() => onPage(page - 1)}>← Prev</button>
      <span className="page-num">
        <span className="page-of">Page</span>
        <input className="page-input" type="text" inputMode="numeric" value={box}
               aria-label="Go to page"
               onChange={(e) => setBox(e.target.value.replace(/\D/g, ""))}
               onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); go(); } }}
               onBlur={go} />
        <span className="page-of">/ {pages}</span>
      </span>
      <button className="btn ghost sm" disabled={page + 1 >= pages} onClick={() => onPage(page + 1)}>Next →</button>
      {onReload && (
        <button className="icon-btn" onClick={onReload} aria-label="Reload"><IconRefresh /></button>
      )}
    </div>
  );
}
