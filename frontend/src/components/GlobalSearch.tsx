/* Global lead search — the topbar search box searches every lead worklist at once
   (name, number, email, city, society, …). Hits show which tab the lead is in;
   picking one navigates to that tab with the query applied so the row is in view.
   On Inventory / Supply the same box keeps filtering that page's own rows, so the
   lead dropdown is suppressed there. */
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { IconSearch } from "./icons";
import { useSearch } from "./SearchContext";
import { useAllLeads } from "../lib/queries";
import { leadMatchesQuery } from "../lib/leads";

const MAX_RESULTS = 8;

export default function GlobalSearch() {
  const { query, setQuery } = useSearch();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [focused, setFocused] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  // Inventory / Supply use this box to filter their own rows — don't hijack it there.
  const globalOn = pathname !== "/inventory" && pathname !== "/supply";
  const q = query.trim();
  const open = globalOn && focused && q.length >= 1;

  const { leads, isLoading } = useAllLeads(open);
  const hits = useMemo(
    () => (open ? leads.filter(({ lead }) => leadMatchesQuery(query, lead)) : []),
    [open, leads, query],
  );
  const results = hits.slice(0, MAX_RESULTS);

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setFocused(false);
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const go = (route: string) => {
    setFocused(false);
    nav(route);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") return setFocused(false);
    if (!open || !results.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); go(results[active].segment.route); }
  };

  return (
    <div className="gsearch" ref={box}>
      <div className="search">
        <IconSearch />
        <input
          placeholder={globalOn ? "Search any lead — name, number, city…" : "Search property, society…"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onKeyDown={onKey}
        />
      </div>
      {open && (
        <div className="gsearch-panel">
          {isLoading && results.length === 0 ? (
            <div className="gsearch-empty">Searching all leads…</div>
          ) : results.length === 0 ? (
            <div className="gsearch-empty">No leads match “{q}”.</div>
          ) : (
            <>
              {results.map((r, i) => (
                <button
                  key={r.lead.id}
                  className={"gsearch-item" + (i === active ? " active" : "")}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => go(r.segment.route)}
                >
                  <div className="gs-main">
                    <span className="gs-name">{r.lead.name || "Unknown lead"}</span>
                    <span className="gs-sub">
                      {[r.lead.phone, r.lead.city, r.lead.society].filter(Boolean).join(" · ") || "—"}
                    </span>
                  </div>
                  <span className="gs-seg">{r.segment.label}</span>
                </button>
              ))}
              {hits.length > results.length && (
                <div className="gsearch-empty">+{hits.length - results.length} more — keep typing to narrow.</div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
