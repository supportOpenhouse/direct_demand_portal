/* Column settings for a lead table: which columns show, and in what order.

   Shown columns are a horizontal row of chips you drag to reorder (native HTML5 drag and
   drop — no library for one list). A focused chip also moves with ← / →, so reordering
   doesn't depend on a mouse.

   Hidden columns split in two, because they mean different things:
     • Table columns          — ones some lead page shows by default
     • From the lead popup    — fields that were only ever visible inside the popup

   Every change applies to the table immediately (behind the modal), so you see the
   result as you arrange it. "Done" just closes. */
import { useState, type DragEvent, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { useModalExit } from "../../lib/useModalExit";
import { IconColumns, IconGrip, IconPlus, IconReset, IconX } from "../../components/icons";
import { LEAD_COLUMNS, COLUMN_BY_ID, type ColumnMeta } from "./columns";
import { useColumnLayout } from "./useColumnLayout";

export function ColumnSettings({
  title, cols, onChange, onReset, isDefault, onClose: rawClose, registry = LEAD_COLUMNS,
}: {
  title: string;
  cols: string[];
  onChange: (next: string[]) => void;
  onReset: () => void;
  isDefault: boolean;
  onClose: () => void;
  /** The columns this table HAS. Defaults to the lead registry; Demand Dashboard
      passes its own, which is what makes this modal reusable rather than lead-only. */
  registry?: ColumnMeta[];
}) {
  const { onClose, overlayClass } = useModalExit(rawClose);
  const byId: Record<string, ColumnMeta> = Object.fromEntries(registry.map((c) => [c.id, c]));
  const [drag, setDrag] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);

  const shown = new Set(cols);
  const hiddenTable = registry.filter((c) => !shown.has(c.id) && !c.popup);
  const hiddenPopup = registry.filter((c) => !shown.has(c.id) && c.popup);

  const move = (from: number, to: number) => {
    if (from === to || to < 0 || to >= cols.length) return;
    const next = [...cols];
    const [id] = next.splice(from, 1);
    next.splice(to, 0, id);
    onChange(next);
  };
  const hide = (id: string) => {
    // a table with no columns renders nothing to click back into — keep at least one
    if (cols.length > 1) onChange(cols.filter((c) => c !== id));
  };
  const show = (id: string) => onChange([...cols, id]);

  const onDragStart = (i: number) => (e: DragEvent) => {
    setDrag(i);
    e.dataTransfer.effectAllowed = "move";
    // Firefox won't start a drag without data set
    e.dataTransfer.setData("text/plain", cols[i]);
  };
  const onDragOver = (i: number) => (e: DragEvent) => {
    e.preventDefault(); // allows the drop
    if (over !== i) setOver(i);
  };
  const onDrop = (i: number) => (e: DragEvent) => {
    e.preventDefault();
    if (drag !== null) move(drag, i);
    setDrag(null); setOver(null);
  };
  const onKey = (i: number) => (e: KeyboardEvent) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); move(i, i - 1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); move(i, i + 1); }
    else if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); hide(cols[i]); }
  };

  return createPortal(
    <div className={overlayClass} onClick={onClose}>
      <div className="modal cs-modal" role="dialog" aria-label="Column settings" onClick={(e) => e.stopPropagation()}>
        <div className="cs-head">
          <div>
            <h3>Columns</h3>
            <div className="cs-sub">{title}</div>
          </div>
          <button className="modal-x" onClick={onClose} aria-label="Close"><IconX /></button>
        </div>

        <div className="cs-body">
          <div className="cs-label">Shown <span>· drag to reorder, or focus one and use ← →</span></div>
          <div className="cs-shown" onDragLeave={() => setOver(null)}>
            {cols.map((id, i) => {
              const c = byId[id];
              if (!c) return null;
              return (
                <div
                  key={id}
                  className={"cs-chip" + (drag === i ? " dragging" : "") + (over === i && drag !== null && drag !== i ? " over" : "")}
                  draggable
                  tabIndex={0}
                  aria-label={`${c.label}, position ${i + 1} of ${cols.length}`}
                  onDragStart={onDragStart(i)}
                  onDragOver={onDragOver(i)}
                  onDrop={onDrop(i)}
                  onDragEnd={() => { setDrag(null); setOver(null); }}
                  onKeyDown={onKey(i)}
                >
                  <span className="cs-grip" aria-hidden><IconGrip /></span>
                  <span className="cs-name">{c.label}</span>
                  <button className="cs-x" onClick={() => hide(id)} disabled={cols.length <= 1}
                    aria-label={`Hide ${c.label}`}
                    title={cols.length <= 1 ? "A table needs at least one column" : `Hide ${c.label}`}>
                    <IconX />
                  </button>
                </div>
              );
            })}
          </div>

          <HiddenGroup label="Hidden table columns" cols={hiddenTable} onShow={show} />
          {/* only where the registry HAS popup fields — on a non-lead table this heading
              would otherwise sit there reading "All shown." about a popup it has none of */}
          {registry.some((c) => c.popup) && (
            <HiddenGroup label="From the lead popup" hint="fields otherwise only visible when you open a lead"
              cols={hiddenPopup} onShow={show} />
          )}
        </div>

        <div className="cs-foot">
          <button className="btn ghost sm" onClick={onReset} disabled={isDefault}
            title={isDefault ? "Already the default layout" : "Back to this page's original columns"}>
            <IconReset /> Reset to default
          </button>
          <button className="btn primary sm" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function HiddenGroup({ label, hint, cols, onShow }: {
  label: string; hint?: string; cols: { id: string; label: string }[]; onShow: (id: string) => void;
}) {
  return (
    <>
      <div className="cs-label">{label}{hint && <span> · {hint}</span>}</div>
      {cols.length === 0
        ? <div className="cs-none">All shown.</div>
        : (
          <div className="cs-hidden">
            {cols.map((c) => (
              <button key={c.id} className="cs-add" onClick={() => onShow(c.id)} title={`Show ${c.label}`}>
                <IconPlus /> {c.label}
              </button>
            ))}
          </div>
        )}
    </>
  );
}

/* Everything a page needs, in one call: the saved layout, the "Columns" button for its
   topbar, and the modal. Each page used to be four near-identical blocks of this. */
export function useLeadColumns(page: string, defaults: string[], title: string,
                               registry: ColumnMeta[] = LEAD_COLUMNS) {
  const layout = useColumnLayout(page, defaults,
    registry === LEAD_COLUMNS ? COLUMN_BY_ID : Object.fromEntries(registry.map((c) => [c.id, c])));
  const [open, setOpen] = useState(false);
  const button = (
    <button className="btn ghost sm" onClick={() => setOpen(true)} title="Choose and reorder columns">
      <IconColumns /> Columns
    </button>
  );
  const modal = open && (
    <ColumnSettings title={title} cols={layout.cols} onChange={layout.setCols} registry={registry}
      onReset={layout.reset} isDefault={layout.isDefault} onClose={() => setOpen(false)} />
  );
  return { cols: layout.cols, button, modal };
}
