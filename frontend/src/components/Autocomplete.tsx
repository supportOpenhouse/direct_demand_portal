/* Debounced async-search chips input. Type → suggestions from the backend; pick
   or free-type + Enter to add. Used for Q4 societies / Q5 localities. */
import { useEffect, useRef, useState } from "react";

export function AutocompleteChips({
  value,
  onChange,
  fetcher,
  placeholder,
  renderHit,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  fetcher: (q: string) => Promise<{ label: string; sub?: string | null }[]>;
  placeholder: string;
  renderHit?: (h: { label: string; sub?: string | null }) => React.ReactNode;
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
