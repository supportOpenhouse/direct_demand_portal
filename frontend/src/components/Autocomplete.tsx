/* Debounced async-search inputs. Type → suggestions from the backend.
   - AutocompleteChips: multi-value (Q4 societies / Q5 localities)
   - AutocompleteInput: single value (source-card society) */
import { useEffect, useRef, useState } from "react";

export function AutocompleteInput({
  value,
  onPick,
  fetcher,
  placeholder,
}: {
  value: string;
  onPick: (label: string, hit?: { label: string; sub?: string | null; meta?: any }) => void;
  fetcher: (q: string) => Promise<{ label: string; sub?: string | null; meta?: any }[]>;
  placeholder: string;
}) {
  const [text, setText] = useState(value);
  const [hits, setHits] = useState<{ label: string; sub?: string | null; meta?: any }[]>([]);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => setText(value), [value]);

  useEffect(() => {
    if (!text.trim() || text === value) {
      setHits([]);
      return;
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        setHits(await fetcher(text.trim()));
        setOpen(true);
      } catch {
        setHits([]);
      }
    }, 200);
    return () => clearTimeout(timer.current);
  }, [text]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("click", onDoc);
    return () => document.removeEventListener("click", onDoc);
  }, []);

  return (
    <div className="ms" ref={box} style={{ position: "relative" }}>
      <input
        value={text}
        placeholder={placeholder}
        onChange={(e) => { setText(e.target.value); onPick(e.target.value); }}
        onFocus={() => hits.length && setOpen(true)}
      />
      {open && hits.length > 0 && (
        <div className="ms-panel" style={{ display: "block" }}>
          {hits.map((h) => (
            <label key={h.label} className="ms-opt" onClick={() => { onPick(h.label, h); setText(h.label); setOpen(false); }}>
              <span>{h.label}{h.sub && <span style={{ color: "var(--muted)", fontSize: 11 }}> · {h.sub}</span>}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export function AutocompleteChips({
  value,
  onChange,
  fetcher,
  placeholder,
  renderHit,
  suggestions = [],
}: {
  value: string[];
  onChange: (v: string[]) => void;
  fetcher: (q: string) => Promise<{ label: string; sub?: string | null }[]>;
  placeholder: string;
  renderHit?: (h: { label: string; sub?: string | null }) => React.ReactNode;
  /** Cascaded options offered as "+" chips — nothing is selected until clicked. */
  suggestions?: string[];
}) {
  const [text, setText] = useState("");
  const [hits, setHits] = useState<{ label: string; sub?: string | null }[]>([]);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (!text.trim()) {
      setHits([]);
      return;
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const r = await fetcher(text.trim());
        setHits(r.filter((h) => !value.includes(h.label)));
        setOpen(true);
      } catch {
        setHits([]);
      }
    }, 200);
    return () => clearTimeout(timer.current);
  }, [text]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("click", onDoc);
    return () => document.removeEventListener("click", onDoc);
  }, []);

  const add = (label: string) => {
    const t = label.trim();
    if (t && !value.includes(t)) onChange([...value, t]);
    setText("");
    setHits([]);
    setOpen(false);
  };

  // a cascade only offers — picking one moves it out of the suggestions into the chips
  const pending = suggestions.filter((s) => !value.includes(s));

  return (
    <div className="ms" ref={box} style={{ position: "relative" }}>
      {value.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
          {value.map((v) => (
            <span key={v} className="bucket-tag" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              {v}
              <span style={{ cursor: "pointer" }} onClick={() => onChange(value.filter((x) => x !== v))}>✕</span>
            </span>
          ))}
        </div>
      )}
      {pending.length > 0 && (
        <div className="sugg-row">
          <span className="sugg-lbl">Suggested</span>
          {pending.map((s) => (
            <button type="button" key={s} className="sugg-chip" onClick={() => onChange([...value, s])}>
              <span className="sc-plus">+</span>{s}
            </button>
          ))}
        </div>
      )}
      <input
        value={text}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onFocus={() => hits.length && setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add(hits[0]?.label || text);
          }
        }}
      />
      {open && hits.length > 0 && (
        <div className="ms-panel" style={{ display: "block" }}>
          {hits.map((h) => (
            <label key={h.label} className="ms-opt" onClick={() => add(h.label)}>
              {renderHit ? renderHit(h) : (
                <span>
                  {h.label}
                  {h.sub && <span style={{ color: "var(--muted)", fontSize: 11 }}> · {h.sub}</span>}
                </span>
              )}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
