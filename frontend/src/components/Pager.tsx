import { useEffect, useState } from "react";
import { IconRefresh } from "./icons";

/* "Showing 1-50 of N" + Prev / Page [n] / N / Next.

   Ported from Direct Inventory's filtered-header. Theirs pages the SERVER; these
   tables are already fully in the client, so this only slices an array -- but the
   control reads the same, which is the point. */
export const PAGE_SIZE = 50;

export function usePaging<T>(rows: T[], size = PAGE_SIZE) {
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(rows.length / size));
  // A filter that shrinks the list can strand you past the end, showing an empty
  // table with rows plainly available behind it.
  useEffect(() => { setPage((p) => Math.min(p, pages - 1)); }, [pages]);
  return { page, setPage, pages, size, slice: rows.slice(page * size, page * size + size) };
}

export function Pager({
  page, pages, size, total, onPage, onReload,
}: {
  page: number; pages: number; size: number; total: number;
  onPage: (p: number) => void;
  onReload?: () => void;
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
      <span className="muted">Showing {first}–{last} of {total.toLocaleString("en-IN")}</span>
      <span className="pager-spacer" />
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
