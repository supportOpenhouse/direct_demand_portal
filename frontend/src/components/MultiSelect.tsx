/* A filter that takes several values at once — a button carrying the count, opening a
   checkbox list. The Filters modal's `<select>`s hold ONE value each; micro-market is
   the case where a person genuinely wants three areas at once, and picking them one
   page-load at a time is the thing that makes a filter not worth using.

   Closes on outside click and on Escape. It is NOT a modal: no overlay, no portal, and
   Escape here must not reach a modal underneath, so the handler stops at this control. */
import { useEffect, useRef, useState } from "react";
import { IconChevronDown, IconX } from "./icons";

export function MultiSelect({
  label, options, value, onChange,
}: {
  label: string;
  /** every option, with its count in the current view */
  options: { value: string; label: string; count?: number }[];
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); } };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc, true);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc, true);
    };
  }, [open]);

  const toggle = (v: string) =>
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);

  const needle = q.trim().toLowerCase();
  const shown = needle ? options.filter((o) => o.label.toLowerCase().includes(needle)) : options;

  return (
    <div className="ms" ref={box}>
      <button className={"btn" + (value.length ? " primary" : " ghost")} onClick={() => setOpen((v) => !v)}
              aria-expanded={open} title={value.length ? value.join(", ") : `Filter by ${label.toLowerCase()}`}>
        {label}{value.length > 0 && ` · ${value.length}`} <IconChevronDown />
      </button>
      {open && (
        <div className="ms-panel">
          <div className="ms-search">
            <input autoFocus value={q} placeholder={`Search ${label.toLowerCase()}…`}
                   onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="ms-list">
            {shown.length === 0 && <div className="ms-none">No match.</div>}
            {shown.map((o) => (
              <label className="ms-row" key={o.value}>
                <input type="checkbox" checked={value.includes(o.value)} onChange={() => toggle(o.value)} />
                <span className="ms-lbl">{o.label}</span>
                {o.count !== undefined && <span className="ms-count">{o.count}</span>}
              </label>
            ))}
          </div>
          {value.length > 0 && (
            <button className="ms-clear" onClick={() => onChange([])}><IconX /> Clear {value.length}</button>
          )}
        </div>
      )}
    </div>
  );
}
