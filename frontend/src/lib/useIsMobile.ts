import { useEffect, useState } from "react";

/* Card-vs-table switch inside a page, at the CRM's 900px breakpoint.

   Not the same thing as the 768px matchMedia in main.tsx — that one picks the whole
   route table once, at boot. This is a live hook: a laptop window dragged narrow has
   to swap the inventory tables for card lists without a reload. */
export default function useIsMobile(bp = 900): boolean {
  const [m, setM] = useState(() => typeof window !== "undefined" && window.innerWidth <= bp);
  useEffect(() => {
    const on = () => setM(window.innerWidth <= bp);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, [bp]);
  return m;
}
