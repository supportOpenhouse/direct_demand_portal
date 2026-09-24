/* "Download CSV" for the Activity Logs page — pick the columns first.

   The list comes from ACTIVITY_EXPORT_FIELDS, the mirror of the server's EXPORT_FIELDS,
   so a column offered here is one the server knows how to write. The file is written in
   that canonical order whatever order you tick them in, so two people's exports line up.

   The picks are remembered in this browser (`dd_activity_export`), because whoever
   exports "with phone and status" does it every week — wrapped in try/catch, so a
   private window just starts from the defaults. */
import { useState } from "react";
import { createPortal } from "react-dom";
import { useModalExit } from "../lib/useModalExit";
import { ACTIVITY_EXPORT_FIELDS } from "../lib/api";
import { IconX } from "./icons";

const KEY = "dd_activity_export";
const DEFAULTS = ACTIVITY_EXPORT_FIELDS.filter(([, , on]) => on).map(([k]) => k);
const KNOWN = new Set(ACTIVITY_EXPORT_FIELDS.map(([k]) => k));

function readSaved(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    // a field removed from the list since it was saved must not ride along
    const ids = (JSON.parse(raw) as unknown[]).filter((x): x is string => typeof x === "string" && KNOWN.has(x));
    return ids.length ? ids : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

export function ExportFieldsModal({ onExport, busy, onClose: raw }: {
  onExport: (fields: string[]) => void;
  busy: boolean;
  onClose: () => void;
}) {
  const { onClose, overlayClass } = useModalExit(raw);
  const [picked, setPicked] = useState<Set<string>>(() => new Set(readSaved()));

  const toggle = (k: string) => {
    const next = new Set(picked);
    if (next.has(k)) next.delete(k); else next.add(k);
    setPicked(next);
  };

  const download = () => {
    const fields = ACTIVITY_EXPORT_FIELDS.map(([k]) => k).filter((k) => picked.has(k));
    try { localStorage.setItem(KEY, JSON.stringify(fields)); } catch { /* used, not saved */ }
    onExport(fields);
  };

  return createPortal(
    <div className={overlayClass} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal xf-modal" role="dialog" aria-label="Download CSV">
        <div className="mh">
          <h3>Download CSV</h3>
          <div className="icon-btn" onClick={onClose}><IconX /></div>
        </div>
        <div className="mb">
          <div className="xf-hint">
            Columns to include. The current filters decide which events go in.
          </div>
          <div className="xf-grid">
            {ACTIVITY_EXPORT_FIELDS.map(([k, label]) => (
              <label key={k} className="xf-opt">
                <input type="checkbox" checked={picked.has(k)} onChange={() => toggle(k)} />
                <span>{label}</span>
                {k === "status_at_time" && (
                  <span className="xf-note">the lead's stage when that event happened</span>
                )}
              </label>
            ))}
          </div>
          <div className="xf-quick">
            <button className="btn ghost sm" onClick={() => setPicked(new Set(KNOWN))}>Select all</button>
            <button className="btn ghost sm" onClick={() => setPicked(new Set(DEFAULTS))}>Defaults</button>
          </div>
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!picked.size || busy} onClick={download}>
            {busy ? "Exporting…" : `Download ${picked.size} column${picked.size === 1 ? "" : "s"}`}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
