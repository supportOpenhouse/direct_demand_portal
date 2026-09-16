/* "Select first N" — the same shortcut wherever rows are picked in bulk.

   Shared rather than re-typed per page so the sizes can't drift: someone who learns
   the shortcut on New Leads finds the same options on WhatsApp.

   A dropdown, not a row of buttons: five sizes as buttons is a toolbar of its own.
   Picking a size REPLACES the selection (useRowSelection.selectFirst) — "first 100" has
   to mean a hundred, not a hundred more. */
import React from "react";

/** `ALL` selects every row currently passing the filters, across all pages. */
export const ALL = "all" as const;
export const SELECT_FIRST_SIZES = [50, 100, 200, 500] as const;

export function SelectFirst(
  { total, onPick, btnClass = "ctl", style }: {
    total: number;
    onPick: (n: number) => void;
    btnClass?: string;
    style?: React.CSSProperties;
  },
) {
  return (
    <select
      className={btnClass}
      style={style}
      value=""
      disabled={total === 0}
      aria-label="Select first N rows"
      title="Replace the selection with the first N rows, in the order shown"
      /* value is pinned to "" so the control reads as an action, not a setting — and so
         picking the same size twice still fires */
      onChange={(e) => {
        const v = e.target.value;
        if (v) onPick(v === ALL ? total : Number(v));
      }}
    >
      <option value="">Select first…</option>
      {SELECT_FIRST_SIZES.map((n) => (
        <option key={n} value={n}>
          {n}{total < n ? ` (all ${total})` : ""}
        </option>
      ))}
      <option value={ALL}>All ({total.toLocaleString("en-IN")})</option>
    </select>
  );
}
