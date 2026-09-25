/* Inline chips + a Filters modal.

   Two jobs that a plain row of <select>s conflates: *what is applied right now*
   (always visible, always one click from removal) and *what could be applied*
   (the long tail, behind a button). The old bar did the second badly — it grew a
   row of dropdowns on every page and still had nowhere to put ranges or dates.

   The page keeps owning its faceting. It passes options already counted by its own
   `pass(l, skip)` call, so the counts stay live and this component stays dumb. */
import { useEffect, useState, type ReactNode } from "react";
import { IconFilter, IconX } from "./icons";
import { DATE_PRESETS, type FilterOption } from "./Filters";

export type FieldKind = "select" | "buttons" | "toggle" | "range" | "date" | "daterange";

export interface Field {
  key: string;
  label: string;
  kind?: FieldKind;                 // default "select"
  options?: FilterOption[];         // select / buttons
  /** How an active value reads on its chip. Defaults to the raw value. */
  format?: (v: any) => string;
  /** Hide the field entirely (segment-specific filters). */
  hidden?: boolean;
  /** buttons only: several can be picked; the value is an array. */
  multi?: boolean;
  /** Fields with the same `row` share ONE full-width line in the modal: each takes its
      content width, the last one takes the rest. */
  row?: string;
}

export type Values = Record<string, any>;

const isSet = (v: any) =>
  v !== "" && v !== null && v !== undefined && v !== false &&
  !(Array.isArray(v) && v.length === 0) &&
  !(typeof v === "object" && !Array.isArray(v) && Object.values(v).every((x) => !x));

const opts = (o: FilterOption[] = []) =>
  o.map((x) => (typeof x === "string" ? { value: x, label: x } : x));

/** Strips the "(12)" a faceted option label carries — a chip shows the filter, not the count. */
const bare = (s: string) => s.replace(/\s*\(\d+\)\s*$/, "");

function chipText(f: Field, v: any): string {
  if (f.format) return f.format(v);
  if (f.kind === "toggle") return f.label;
  if (f.multi) return `${f.label}: ${opts(f.options).filter((o) => v.includes(o.value)).map((o) => bare(o.label)).join(", ")}`;
  if (f.kind === "range") return `${f.label} ${v.min || "0"}–${v.max || "∞"}`;
  if (f.kind === "daterange") {
    if (v.preset === "custom") return `${f.label}: ${v.from || "…"} – ${v.to || "…"}`;
    return `${f.label}: ${DATE_PRESETS.find((p) => p.value === v.preset)?.label ?? v.preset}`;
  }
  const hit = opts(f.options).find((o) => o.value === v);
  return `${f.label}: ${bare(hit?.label ?? String(v))}`;
}

export function FilterBar({
  fields, values, onChange, onClear, children,
}: {
  fields: Field[];
  values: Values;
  onChange: (key: string, value: any) => void;
  onClear: () => void;
  /** Anything that belongs beside the button — export, bulk actions. */
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const shown = fields.filter((f) => !f.hidden);
  const active = shown.filter((f) => isSet(values[f.key]));

  return (
    <>
      <div className="fbar">
        <button className={"btn sm" + (active.length ? "" : " ghost")} onClick={() => setOpen(true)}>
          <IconFilter /> Filters
          {active.length > 0 && <span className="fbar-count">{active.length}</span>}
        </button>
        {children}
      </div>

      {active.length > 0 && (
        <div className="fchips">
          {active.map((f) => (
            <button key={f.key} className="fchip" onClick={() => onChange(f.key, reset(f))}
                    title={`Remove ${f.label} filter`}>
              {chipText(f, values[f.key])}
              <IconX />
            </button>
          ))}
          <button className="fchip-clear" onClick={onClear}>Clear all</button>
        </div>
      )}

      {open && (
        <FilterModal fields={shown} values={values} onChange={onChange}
                     onClear={onClear} onClose={() => setOpen(false)} />
      )}
    </>
  );
}

const reset = (f: Field) =>
  f.multi ? []
  : f.kind === "toggle" ? false
  : f.kind === "range" ? { min: "", max: "" }
  : f.kind === "daterange" ? { preset: "", from: "", to: "" }
  : "";

function FilterModal({ fields, values, onChange, onClear, onClose }: {
  fields: Field[]; values: Values;
  onChange: (k: string, v: any) => void; onClear: () => void; onClose: () => void;
}) {
  // Esc closes. Filters apply live, so there is no Cancel to restore to — the chips
  // outside are the undo, which is the whole point of showing them.
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  return (
    <div className="overlay show" onClick={onClose}>
      <div className="modal" style={{ width: "min(620px,100%)" }} onClick={(e) => e.stopPropagation()}>
        <div className="mh">
          <h3>Filters</h3>
          <div className="icon-btn" onClick={onClose}><IconX /></div>
        </div>
        <div className="mb">
          <div className="fgrid">
            {groups(fields).map((g) => g.length > 1 ? (
              <div key={g[0].row} className="frow">{g.map(renderField)}</div>
            ) : renderField(g[0]))}
          </div>
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClear}>Clear all</button>
          <button className="btn primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );

  function renderField(f: Field) {
    return (
              /* A custom date range is two date inputs side by side, and a date input won't
                 shrink below its natural width — in one 190px grid track the "to" box spilled
                 into the next cell, which painted over it and took its clicks. Span the row. */
              <div className="field" key={f.key}
                   style={{ marginBottom: 0,
                            gridColumn: f.kind === "daterange" && values[f.key]?.preset === "custom" ? "1 / -1" : undefined }}>
                <label>{f.label}</label>
                {f.kind === "toggle" ? (
                  <button className={"btn sm" + (values[f.key] ? "" : " ghost")}
                          onClick={() => onChange(f.key, !values[f.key])}>
                    {values[f.key] ? "On" : "Off"}
                  </button>
                ) : f.kind === "range" ? (
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <input type="number" placeholder="min" value={values[f.key]?.min ?? ""}
                           onChange={(e) => onChange(f.key, { ...values[f.key], min: e.target.value })} />
                    <span style={{ color: "var(--muted)" }}>–</span>
                    <input type="number" placeholder="max" value={values[f.key]?.max ?? ""}
                           onChange={(e) => onChange(f.key, { ...values[f.key], max: e.target.value })} />
                  </div>
                ) : f.kind === "daterange" ? (
                  /* A preset, or a custom from–to. Picking a preset clears the custom
                     dates, so a stale range can't sit hidden behind "This week". */
                  <div>
                    <select value={values[f.key]?.preset ?? ""}
                            onChange={(e) => onChange(f.key, { preset: e.target.value, from: "", to: "" })}>
                      <option value="">All</option>
                      {DATE_PRESETS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                    </select>
                    {values[f.key]?.preset === "custom" && (
                      <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 6 }}>
                        <input type="date" value={values[f.key]?.from ?? ""}
                               onChange={(e) => onChange(f.key, { ...values[f.key], from: e.target.value })} />
                        <span style={{ color: "var(--muted)" }}>–</span>
                        <input type="date" value={values[f.key]?.to ?? ""}
                               onChange={(e) => onChange(f.key, { ...values[f.key], to: e.target.value })} />
                      </div>
                    )}
                  </div>
                ) : f.kind === "buttons" ? (
                  /* one button per option; the picked one is the accent (there is no
                     .btn.active — it has to change class), and picking it again clears it */
                  <div className="fbtns">
                    {opts(f.options).map((o) => {
                      const cur = values[f.key];
                      const on = f.multi ? (cur ?? []).includes(o.value) : cur === o.value;
                      const next = f.multi
                        ? (on ? cur.filter((x: string) => x !== o.value) : [...(cur ?? []), o.value])
                        : (on ? "" : o.value);
                      return (
                        <button key={o.value} className={"btn sm " + (on ? "primary" : "ghost")}
                                onClick={() => onChange(f.key, next)}>
                          {o.label}
                        </button>
                      );
                    })}
                  </div>
                ) : f.kind === "date" ? (
                  <input type="date" value={values[f.key] ?? ""} onChange={(e) => onChange(f.key, e.target.value)} />
                ) : (
                  <select value={values[f.key] ?? ""} onChange={(e) => onChange(f.key, e.target.value)}>
                    <option value="">All</option>
                    {opts(f.options).map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                )}
              </div>
    );
  }
}

/* Consecutive fields sharing a `row` key become one group; everything else stands alone. */
function groups(fields: Field[]): Field[][] {
  const out: Field[][] = [];
  for (const f of fields) {
    const last = out[out.length - 1];
    if (f.row && last && last[0].row === f.row) last.push(f);
    else out.push([f]);
  }
  return out;
}

/** One filter object + a setter, so a page holds filters in one piece of state. */
export function useFilterValues<T extends Values>(initial: T) {
  const [values, setValues] = useState<T>(initial);
  const set = (k: string, v: any) => setValues((p) => ({ ...p, [k]: v }));
  const clear = () => setValues(initial);
  return { values, set, clear, setValues };
}
