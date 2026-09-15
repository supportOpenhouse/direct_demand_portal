/* Opening a lead is a popup, not a page.

   The route `/leads/:id` still exists and still renders the full page — that's what a
   pasted link, a new tab, and the Report drill-down's `target="_blank"` all need. What
   changed is the in-app click: it opens the same component over the list you were
   reading, so you don't lose your filters, your scroll position, or your place. */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode, type MouseEvent } from "react";
import { api } from "../lib/api";
import LeadDetail from "../pages/LeadDetail";
import { useModalExit } from "../lib/useModalExit";
import { IconX } from "./icons";

const Ctx = createContext<(id: string) => void>(() => {});
export const useOpenLead = () => useContext(Ctx);

export function LeadModalProvider({ children }: { children: ReactNode }) {
  const [id, setId] = useState<string | null>(null);
  const open = useCallback((leadId: string) => setId(leadId), []);
  return (
    <Ctx.Provider value={open}>
      {children}
      {id && <LeadPopup id={id} onClose={() => setId(null)} />}
    </Ctx.Provider>
  );
}

function LeadPopup({ id, onClose: rawClose }: { id: string; onClose: () => void }) {
  const { onClose, overlayClass } = useModalExit(rawClose);

  /* Record the open. Fire-and-forget on purpose: this is telemetry, and a lead that
     refuses to open because its logging call failed would be a far worse bug than a
     missing row. The server dedupes repeat opens, so no debounce is needed here. */
  useEffect(() => { api.leadViewed(id).catch(() => {}); }, [id]);
  return (
    <div className={overlayClass} onClick={onClose}>
      <div className="modal modal-lead" onClick={(e) => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose} aria-label="Close"><IconX /></button>
        <div className="modal-lead-body">
          <LeadDetail leadId={id} inModal />
        </div>
      </div>
    </div>
  );
}

/** Row-click props that open the lead popup.

    A row carries call buttons, checkboxes, note toggles and links; their clicks
    bubble to the row, so opening on ANY click means pressing Call also opens the
    popup behind it. Guarding once on the way out beats a stopPropagation on every
    interactive cell — which is what the older tables do, and what gets forgotten
    the next time a control is added to a row. */
export function useRowOpen() {
  const open = useOpenLead();
  return (id: string) => ({
    className: "lead-row",
    onClick: (e: MouseEvent<HTMLTableRowElement>) => {
      if ((e.target as HTMLElement).closest("button, a, input, select, textarea, label")) return;
      open(id);
    },
  });
}

/** A lead link that opens the popup on a plain click but stays a real anchor.
    Middle-click, ⌘/Ctrl-click and "open in new tab" still load the full page —
    intercepting those would take away a way of working people already have. */
export function LeadLink({
  id, className, style, title, children,
}: { id: string; className?: string; style?: React.CSSProperties; title?: string; children: ReactNode }) {
  const open = useOpenLead();
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    open(id);
  };
  return (
    <a href={`/leads/${id}`} onClick={onClick} className={className} style={style} title={title}>
      {children}
    </a>
  );
}
