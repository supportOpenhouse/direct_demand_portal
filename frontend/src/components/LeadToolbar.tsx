/* One toolbar for every page that lists leads.

   Replaces the topbar's global search: a search box that lives on the page it
   filters can say what it searches, and cannot leave a hidden query applied to a
   list you walked away from, which is what the global one did.

   Layout follows Direct Inventory's board toolbar:
     [ city tabs ] [ search ][ Search ] [ Filters ] [ extras ]

   Select is NOT here — it lives on the Pager, beside "Showing 1–50 of N" (16 Sep).

   The search box is the ONE search on a lead page (12 Oct):
     · plain text, as always — or field search `field:"text" AND …` (lib/leadQuery.ts):
       it suggests field names, then that field's values, and offers +AND | +OR once the
       cursor sits after a finished clause;
     · everyone gets the Claude mascot to its right (admins only until 13 Oct) — grey = plain search, Claude orange =
       the box's text goes to Claude, which reads every lead this page could show and
       returns the matches. Claude's comments and every error open a popup; the server
       logs every Claude search to activity_log. */
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import SlideTabs from "./SlideTabs";
import { FilterBar, type Field, type Values } from "./FilterBar";
import { ClaudeMascot, IconSearch, IconX } from "./icons";
import type { Lead } from "../lib/api";
import { useClaudeSearch } from "../lib/queries";
import { useModalExit } from "../lib/useModalExit";
import {
  NO_SEARCH, cursorContext, fieldSuggestions, parseQuery, valueSuggestions, type LeadSearch,
} from "../lib/leadQuery";

/* The three cities the team actually works. Anything else -- a typo, a sheet
   formula error (#N/A), or a blank -- is "Invalid City", which is the only way
   those rows are reachable at all: they match no city tab, and before this
   nothing surfaced them. */
export const CITY_TABS = ["Gurgaon", "Noida", "Ghaziabad"];
export const INVALID_CITY = " invalid";
const VALID = new Set(CITY_TABS.map((c) => c.toLowerCase()));

/** "" = All, a city name = that city, INVALID_CITY = null/blank/anything else. */
export function cityMatches(city: string | null | undefined, sel: string): boolean {
  if (!sel) return true;
  const v = (city ?? "").trim().toLowerCase();
  if (sel === INVALID_CITY) return !VALID.has(v);
  return v === sel.toLowerCase();
}

export function LeadToolbar({
  city, onCity, search, onSearch, segment = null, leads = [],
  placeholder = 'Search any field — e.g. 1709 Sahaj, or city:"noida" AND rm:"saumya"',
  fields, values, onChange, onClear,
  children,
}: {
  city: string;
  onCity: (c: string) => void;
  /** The APPLIED search. The box holds its own draft until Search/Enter. */
  search: LeadSearch;
  onSearch: (s: LeadSearch) => void;
  /** the SEGMENTS key this page lists — Claude searches only those; null = every stage */
  segment?: string | null;
  /** the page's leads, for the value suggestions of field search */
  leads?: Lead[];
  placeholder?: string;
  fields: Field[];
  values: Values;
  onChange: (k: string, v: any) => void;
  onClear: () => void;
  children?: ReactNode;
}) {
  const [claude, setClaude] = useState(false);
  const claudeOn = claude;
  const ask = useClaudeSearch();
  const [popup, setPopup] = useState<{ title: string; text: string } | null>(null);

  const [draft, setDraft] = useState(search.q);
  const [caret, setCaret] = useState(0);
  const [focused, setFocused] = useState(false);
  const [hi, setHi] = useState(-1);
  const input = useRef<HTMLInputElement>(null);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const q = draft.trim();
    setHi(-1);
    if (!claudeOn) { onSearch({ q, claudeIds: null }); return; }
    if (q.length < 2 || ask.isPending) return;
    ask.mutate({ query: q, segment }, {
      onSuccess: (r) => {
        onSearch({ q, claudeIds: new Set(r.lead_ids) });
        if (r.note) setPopup({ title: "Claude says", text: r.note });
      },
      onError: (err) => setPopup({ title: "Claude search failed", text: (err as Error).message }),
    });
  };
  const clear = () => { setDraft(""); onSearch(NO_SEARCH); };

  /* Replace draft[from, to) with `text`, parking the cursor `at` characters into it. */
  const put = (from: number, to: number, text: string, at = text.length) => {
    const next = draft.slice(0, from) + text + draft.slice(to);
    const c = from + at;
    setDraft(next);
    setCaret(c);
    requestAnimationFrame(() => { input.current?.focus(); input.current?.setSelectionRange(c, c); });
  };

  // field-search help — plain mode only; Claude mode is free text
  const ctx = claudeOn ? ({ kind: "none" } as const) : cursorContext(draft, caret);
  const options = useMemo(() => {
    if (ctx.kind === "value") {
      const close = draft.indexOf('"', caret);   // close the quote that's there, don't add one
      const to = close === -1 ? caret : close + 1;
      return valueSuggestions(leads, ctx.field, ctx.partial).map((v) => ({
        key: v.value, label: v.value, hint: v.count.toLocaleString("en-IN"),
        apply: () => put(ctx.from, to, `${v.value}" `),
      }));
    }
    // field names only once something is typed — an empty box isn't asking for them
    if (ctx.kind === "field" && (ctx.partial || draft.trim())) {
      return fieldSuggestions(ctx.partial).slice(0, 8).map((f) => ({
        key: f.key, label: `${f.key}:`, hint: f.label,
        apply: () => put(ctx.from, caret, `${f.key}:""`, f.key.length + 2),
      }));
    }
    return [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, caret, leads, claudeOn]);
  useEffect(() => setHi(-1), [draft, caret]);
  const showList = focused && options.length > 0;
  const errors = useMemo(
    () => (!claudeOn && /\w+\s*:|"/.test(draft) ? parseQuery(draft).errors : []), [draft, claudeOn]);

  const join = (op: "AND" | "OR") => {
    const end = draft.slice(0, caret).replace(/\s+$/, "").length;
    put(end, caret, ` ${op} `);
  };
  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showList) { if (e.key === "Escape") input.current?.blur(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => (h + 1) % options.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => (h <= 0 ? options.length - 1 : h - 1)); }
    // Tab always takes a suggestion; Enter only one you've arrowed to — otherwise Enter
    // searches, so typing "na" and pressing Enter still searches for "na"
    else if (e.key === "Tab" || (e.key === "Enter" && hi >= 0)) { e.preventDefault(); options[Math.max(hi, 0)].apply(); }
    else if (e.key === "Escape") setFocused(false);
  };
  const track = (e: React.SyntheticEvent<HTMLInputElement>) => setCaret(e.currentTarget.selectionStart ?? 0);
  const applied = search.q || search.claudeIds;

  return (
    <div className="lead-toolbar">
      <SlideTabs className="city-tabs" activeSelector=".tab-active">
        <button className={!city ? "tab tab-active" : "tab"} onClick={() => onCity("")}>All</button>
        {CITY_TABS.map((c) => (
          <button key={c} className={city === c ? "tab tab-active" : "tab"} onClick={() => onCity(c)}>{c}</button>
        ))}
        <button className={city === INVALID_CITY ? "tab tab-active" : "tab"}
                onClick={() => onCity(INVALID_CITY)}
                title="No city, or a value that is not one of the three - includes sheet errors like #N/A">
          Invalid City
        </button>
      </SlideTabs>

      <form className={"search-form" + (claudeOn ? " claude" : "")} onSubmit={submit}>
        <div className="ls-box">
          <input ref={input} value={draft} spellCheck={false} readOnly={ask.isPending}
            placeholder={claudeOn ? "Describe the leads — e.g. hot buyers who asked for a weekend visit" : placeholder}
            onChange={(e) => { setDraft(e.target.value); setCaret(e.target.selectionStart ?? 0); }}
            onSelect={track} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} onKeyDown={onKey} />
          {showList && (
            <div className="ls-suggest" role="listbox">
              {options.map((o, i) => (
                /* mousedown + preventDefault: pick before the input's blur closes the list */
                <div key={o.key} role="option" aria-selected={i === hi}
                  className={"ls-opt" + (i === hi ? " on" : "")}
                  onMouseEnter={() => setHi(i)} onMouseDown={(e) => { e.preventDefault(); o.apply(); }}>
                  <span className="ls-opt-l">{o.label}</span>
                  <span className="ls-opt-h">{o.hint}</span>
                </div>
              ))}
            </div>
          )}
          {focused && !showList && ctx.kind === "joiner" && (
            <div className="ls-join">
              <button type="button" className="ls-chip" onMouseDown={(e) => { e.preventDefault(); join("AND"); }}>+AND</button>
              <span className="ls-sep">|</span>
              <button type="button" className="ls-chip" onMouseDown={(e) => { e.preventDefault(); join("OR"); }}>+OR</button>
            </div>
          )}
          {focused && !showList && ctx.kind !== "joiner" && errors.length > 0 && (
            <div className="ls-join ls-err">{errors.join(" · ")}</div>
          )}
        </div>
        <button type="button" className={"claude-toggle" + (claudeOn ? " on" : "")}
          aria-pressed={claudeOn} disabled={ask.isPending}
          title={claudeOn ? "Claude search is on — click for normal search" : "Search with Claude"}
          onClick={() => setClaude((v) => !v)}>
          <ClaudeMascot />
        </button>
        <button type="submit" className="btn primary" disabled={ask.isPending}>
          <IconSearch /> {ask.isPending ? "Claude is searching…" : "Search"}
        </button>
        {applied && (
          <button type="button" className="btn ghost" onClick={clear}>
            <IconX /> Clear
          </button>
        )}
      </form>

      <FilterBar fields={fields} values={values} onChange={onChange} onClear={onClear}>
        {children}
      </FilterBar>
      {popup && <ClaudePopup title={popup.title} text={popup.text} onClose={() => setPopup(null)} />}
    </div>
  );
}

/* Anything a Claude search says besides its matches — a comment, "that isn't a search",
   an error. Portaled: the toolbar sits under elements that would clip or stack over it. */
function ClaudePopup({ title, text, onClose: rawClose }: { title: string; text: string; onClose: () => void }) {
  const { onClose, overlayClass } = useModalExit(rawClose);
  return createPortal(
    <div className={overlayClass} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ width: "min(480px,100%)" }} role="dialog" aria-label={title}>
        <div className="mh">
          <h3 className="claude-pop-h"><ClaudeMascot /> {title}</h3>
          <div className="icon-btn" onClick={onClose}><IconX /></div>
        </div>
        <div className="mb claude-pop-t">{text}</div>
        <div className="mf"><button className="btn" onClick={onClose}>OK</button></div>
      </div>
    </div>,
    document.body,
  );
}
