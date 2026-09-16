/* The one lead table. Header, cells, empty state and loading rows all come from the same
   list of column ids, so the span of the empty-state row can no longer disagree with the
   number of headers — which is what hand-counting `colSpan` in four files kept getting
   wrong every time a column was added. */
import type { ReactNode } from "react";
import type { Lead } from "../../lib/api";
import { SortTh } from "../../lib/useSort";
import { SkeletonTable } from "../../components/Skeleton";
import { COLUMN_BY_ID, type LeadColCtx } from "./columns";

interface Selection {
  has: (id: string) => boolean;
  toggle: (id: string) => void;
  toggleAll: () => void;
  allChecked: boolean;
}

export function LeadTable({
  cols, rows, ctx = {}, sortKey, dir, onSort, selectMode = false, sel,
  isLoading, empty, rowProps, skeletonRows = 8,
}: {
  cols: string[];
  rows: Lead[];
  ctx?: LeadColCtx;
  sortKey: string | null;
  dir: "asc" | "desc";
  onSort: (k: string) => void;
  selectMode?: boolean;
  sel?: Selection;
  isLoading: boolean;
  /** shown when there are no rows */
  empty: ReactNode;
  /** row-click props, from useRowOpen() */
  rowProps: (id: string) => Record<string, unknown>;
  skeletonRows?: number;
}) {
  const columns = cols.map((id) => COLUMN_BY_ID[id]).filter(Boolean);
  const checkbox = selectMode && sel;
  const span = columns.length + (checkbox ? 1 : 0);

  return (
    <table>
      <thead>
        <tr>
          {checkbox && (
            <th style={{ width: 30 }}>
              <input type="checkbox" checked={sel.allChecked} onChange={sel.toggleAll}
                style={{ accentColor: "var(--emerald)", cursor: "pointer" }} title="Select all" />
            </th>
          )}
          {columns.map((c) => c.sort
            ? <SortTh key={c.id} label={c.label} sortKey={c.id} activeKey={sortKey} dir={dir} onSort={onSort} style={c.thStyle} />
            : <th key={c.id} style={c.thStyle}>{c.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {isLoading ? (
          <SkeletonTable rows={skeletonRows} cols={span} />
        ) : rows.length === 0 ? (
          <tr><td colSpan={span}><div className="empty" style={{ padding: 30 }}>{empty}</div></td></tr>
        ) : (
          rows.map((l) => (
            <tr key={l.id} {...rowProps(l.id)}>
              {checkbox && (
                <td onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={sel.has(l.id)} onChange={() => sel.toggle(l.id)}
                    style={{ accentColor: "var(--emerald)", cursor: "pointer" }} />
                </td>
              )}
              {columns.map((c) => (
                <td key={c.id} className={c.tdClass} style={c.tdStyle}
                  /* interactive cells hold buttons / pickers whose clicks would otherwise
                     bubble to the row and open the lead popup behind them */
                  onClick={c.interactive ? (e) => e.stopPropagation() : undefined}>
                  {c.render(l, ctx)}
                </td>
              ))}
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}
