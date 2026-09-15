import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

/* Wraps a segmented toggle and adds a thumb that SLIDES to the active option
   instead of the background snapping between buttons.

   Deliberately a wrapper, not an options-driven control: a call site keeps its own
   button markup and just swaps <div> for <SlideTabs>. The active button is found by
   class and a MutationObserver re-measures when that class flips, so there's no
   value/onChange plumbing to thread through. Ported from Direct Inventory. */
export default function SlideTabs({
  className = "", activeSelector = "button.on", children,
}: { className?: string; activeSelector?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState({ left: 0, width: 0, ready: false });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => {
      const active = el.querySelector(activeSelector);
      if (!active) { setThumb((p) => (p.ready ? { ...p, ready: false } : p)); return; }
      const c = el.getBoundingClientRect();
      const b = active.getBoundingClientRect();
      const left = b.left - c.left, width = b.width;
      setThumb((p) => (p.left === left && p.width === width && p.ready ? p : { left, width, ready: true }));
    };
    measure();
    const ro = new ResizeObserver(measure); ro.observe(el);
    const mo = new MutationObserver(measure);
    mo.observe(el, { attributes: true, subtree: true, attributeFilter: ["class"] });
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [activeSelector, children]);

  return (
    <div ref={ref} className={`${className} seg-slide`}>
      <span className="seg-thumb" aria-hidden="true"
            style={{ transform: `translateX(${thumb.left}px)`, width: thumb.width, opacity: thumb.ready ? 1 : 0 }} />
      {children}
    </div>
  );
}
