import { useEffect, useRef, useState } from 'react';
import { IconChevron } from './icons';

export interface MultiSelectProps {
  options: string[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  /** Adds .invalid to the toggle (422 field errors). */
  invalid?: boolean;
}

/**
 * .ms multi-select dropdown (Q4/Q5): field-styled toggle with selection
 * summary, accent ring when open, checkbox rows, closes on outside click.
 */
export function MultiSelect({ options, value, onChange, placeholder, invalid }: MultiSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDocDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocDown);
    return () => document.removeEventListener('mousedown', onDocDown);
  }, [open]);

  const toggle = (opt: string) => {
    onChange(value.includes(opt) ? value.filter((v) => v !== opt) : [...value, opt]);
  };

  const summary =
    value.length === 0
      ? null
      : value.length <= 2
        ? value.join(', ')
        : `${value.length} selected`;

  return (
    <div className={`ms${open ? ' open' : ''}`} ref={rootRef}>
      <button
        type="button"
        className={`ms-toggle${invalid ? ' invalid' : ''}`}
        onClick={() => setOpen((o) => !o)}
      >
        {summary ? <span>{summary}</span> : <span className="ms-ph">{placeholder ?? 'Select…'}</span>}
        <IconChevron size={14} className="chev" />
      </button>
      {open && (
        <div className="ms-panel">
          {options.length === 0 && <div className="empty">No options</div>}
          {options.map((opt) => (
            <label key={opt} className="ms-opt">
              <input type="checkbox" checked={value.includes(opt)} onChange={() => toggle(opt)} />
              <span>{opt}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
