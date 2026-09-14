import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/* Renders its children into the topbar's action strip.

   The strip is the page's action bar: buttons that act on THIS page (Select,
   Download CSV) belong there rather than repeated into every toolbar. The slot is
   found on mount rather than at module load, because the topbar mounts with the
   shell and a page can render before that in a fresh route. */
export function TopbarSlot({ children }: { children: ReactNode }) {
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  useEffect(() => { setSlot(document.getElementById("topbar-slot")); }, []);
  return slot ? createPortal(children, slot) : null;
}
