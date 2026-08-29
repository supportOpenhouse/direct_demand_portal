/* "Select first N" — the same shortcut wherever rows are picked in bulk.

   Shared rather than re-typed per page so the sizes can't drift: someone who learns
   the shortcut on New Leads finds the same two buttons on WhatsApp. */
import React from "react";

export const SELECT_FIRST_SIZES = [10, 25];

export function SelectFirst(
  { total, onPick, btnClass = "btn ghost sm", style }: {
    total: number;
    onPick: (n: number) => void;
    btnClass?: string;
    style?: React.CSSProperties;
  },
) {
  return (
    <>
      {SELECT_FIRST_SIZES.map((n) => (
        <button key={n} className={btnClass} style={style} disabled={total === 0}
          onClick={() => onPick(n)}
          title={total < n
            ? `Only ${total} row${total === 1 ? "" : "s"} here — selects all of them`
            : `Replace the selection with the first ${n} rows`}>
          Select first {n}
        </button>
      ))}
    </>
  );
}
