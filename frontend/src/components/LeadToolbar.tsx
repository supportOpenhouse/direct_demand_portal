/* One toolbar for every page that lists leads.

   Replaces the topbar's global search: a search box that lives on the page it
   filters can say what it searches, and cannot leave a hidden query applied to a
   list you walked away from, which is what the global one did.

   Layout follows Direct Inventory's board toolbar:
     [ city tabs ] [ search ][ Search ] [ Filters ] [ Select ] [ extras ] */
import { useState, type FormEvent, type ReactNode } from "react";
import SlideTabs from "./SlideTabs";
import { FilterBar, type Field, type Values } from "./FilterBar";
import { SelectFirst } from "./SelectFirst";
import { IconSearch, IconX } from "./icons";

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
  city, onCity, q, onQ, placeholder = "Search any lead - name, number, city, society",
  fields, values, onChange, onClear,
  selectMode, onSelectMode, selectTotal = 0, onSelectFirst, children,
}: {
  city: string;
  onCity: (c: string) => void;
  /** The APPLIED query. The box holds its own draft until Search/Enter. */
  q: string;
  onQ: (q: string) => void;
  placeholder?: string;
  fields: Field[];
  values: Values;
  onChange: (k: string, v: any) => void;
  onClear: () => void;
  /** Omit the whole group to hide Select (pages with no bulk actions). */
  selectMode?: boolean;
  onSelectMode?: (on: boolean) => void;
  selectTotal?: number;
  onSelectFirst?: (n: number) => void;
  children?: ReactNode;
}) {
  const [draft, setDraft] = useState(q);
  const submit = (e: FormEvent) => { e.preventDefault(); onQ(draft.trim()); };

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

      <form className="search-form" onSubmit={submit}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={placeholder} />
        <button type="submit" className="btn primary"><IconSearch /> Search</button>
        {q && (
          <button type="button" className="btn ghost" onClick={() => { setDraft(""); onQ(""); }}>
            <IconX /> Clear
          </button>
        )}
      </form>

      <FilterBar fields={fields} values={values} onChange={onChange} onClear={onClear}>
        {onSelectMode && (
          <>
            <button className={"btn sm" + (selectMode ? "" : " ghost")} onClick={() => onSelectMode(!selectMode)}>
              {selectMode ? "Exit Select" : "Select"}
            </button>
            {/* the 10/25 shortcuts only mean anything once rows can be picked */}
            {selectMode && onSelectFirst && (
              <SelectFirst total={selectTotal} onPick={onSelectFirst} btnClass="btn ghost sm" />
            )}
          </>
        )}
        {children}
      </FilterBar>
    </div>
  );
}
