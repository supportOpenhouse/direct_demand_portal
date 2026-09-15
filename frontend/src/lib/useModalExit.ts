import { useCallback, useEffect, useRef, useState } from "react";

/* Must match the exit animation duration in app.css (.overlay.closing). */
const EXIT_MS = 240;

/* Only the TOPMOST modal reacts to Escape — otherwise a stacked pair (the lead
   popup with the reject modal over it) would both close at once. */
const stack: object[] = [];

const instant = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * Animated close + stack-aware Escape. Use it by SHADOWING the raw prop, so every
 * existing `onClose` call inside the component animates without being touched:
 *
 *   function Foo({ onClose: rawClose }) {
 *     const { onClose, overlayClass } = useModalExit(rawClose);
 *
 * The real `rawClose` (which unmounts us) fires only after the exit animation, so
 * the element is still mounted while it plays. Ported from Direct Inventory.
 */
export function useModalExit(rawClose: () => void) {
  const [closing, setClosing] = useState(false);
  const closingRef = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const onClose = useCallback(() => {
    if (closingRef.current) return;        // ignore repeat presses mid-exit
    closingRef.current = true;
    setClosing(true);
    timer.current = setTimeout(rawClose, instant() ? 0 : EXIT_MS);
  }, [rawClose]);

  useEffect(() => () => clearTimeout(timer.current), []);

  useEffect(() => {
    const token = {};
    stack.push(token);
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (stack[stack.length - 1] !== token) return;   // not the top modal
      e.stopPropagation();
      onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const i = stack.indexOf(token);
      if (i >= 0) stack.splice(i, 1);
    };
  }, [onClose]);

  return { onClose, closing, overlayClass: "overlay show" + (closing ? " closing" : "") };
}
