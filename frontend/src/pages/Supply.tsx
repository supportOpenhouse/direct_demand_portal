/* Supply Pipeline — table with topbar search, stage filter pills, and city/config filters. */
import { useState } from "react";
import { useSupply, formatPrice } from "../lib/queries";
import { SupplyItem } from "../lib/api";
import { useSearch, matches } from "../components/SearchContext";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { useSort, SortTh } from "../lib/useSort";
import { useAuth } from "../components/AuthContext";

/* closest-to-landing first — 'Visited' dominates the table (900+ rows), so the
   advanced stages must surface above it */
const STAGE_ORDER = ["Token Req", "AMA Signed", "AMA Req", "Deal Terms", "Visited"];

function unitText(s: SupplyItem, showUnit: boolean): string {
  const parts = [
    s.raw.tower_no?.trim() && `Tower ${s.raw.tower_no.trim()}`,
    showUnit && s.raw.unit_no?.trim() && `Unit ${s.raw.unit_no.trim()}`,
    s.raw.floor?.trim() && `Floor ${s.raw.floor.trim()}`,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

export default function Supply() {
  const { data, isLoading } = useSupply();
  const { query } = useSearch();
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  const [stage, setStage] = useState("");
  const [city, setCity] = useState("");
  const [config, setConfig] = useState("");

  const all = data?.items ?? [];
  const base = all
    .filter(
      (s) =>
        (!stage || s.stage === stage) &&
        (!city || s.city === city) &&
        (!config || s.configuration === config) &&
        matches(query, s.id, s.society, s.locality, s.city, s.configuration, s.stage)
    )
    .sort((a, b) => STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage));

  // default (no column picked) keeps the closest-to-landing stage order above
  const { sorted: items, sortKey, dir, onSort } = useSort<SupplyItem>(base, {
    uid: (s) => s.id,
    society: (s) => s.society,
    locality: (s) => s.locality,
    city: (s) => s.city,
    config: (s) => s.configuration,
    area: (s) => s.area_sqft,
    price: (s) => s.price_lacs,
    stage: (s) => STAGE_ORDER.indexOf(s.stage),
  });

  const countOf = (st: string) => all.filter((s) => s.stage === st).length;

  return (
    <>
      <div className="section-head">
        <p className="sec-sub" style={{ margin: 0 }}>
          Units still in the pipeline — closest to landing first.
          {data?.status === "ok" && (
            <>
              {" "}
              <b style={{ color: "var(--ink-2)" }}>
                {items.length !== all.length ? `${items.length} of ${all.length}` : all.length} units
              </b>{" "}
              live from the Supply Closure Tracker.
            </>
          )}
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <FilterSelect label="City" value={city} options={uniqueValues(all, (s) => s.city)} onChange={setCity} width={130} />
          <FilterSelect label="Config" value={config} options={uniqueValues(all, (s) => s.configuration)} onChange={setConfig} width={130} />
          {(stage || city || config) && (
            <button
              className="btn ghost sm"
              onClick={() => {
                setStage("");
                setCity("");
                setConfig("");
              }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="tabs">
        <div className={"tab" + (stage === "" ? " active" : "")} onClick={() => setStage("")}>
          All
        </div>
        {STAGE_ORDER.map((st) => (
          <div key={st} className={"tab" + (stage === st ? " active" : "")} onClick={() => setStage(st)}>
            {st}{" "}
            <span style={{ fontFamily: "'Spline Sans Mono'", fontSize: 11, color: "var(--muted)" }}>
              {countOf(st)}
            </span>
          </div>
        ))}
      </div>

      <div className="card">
        {isLoading ? (
          <div className="empty" style={{ padding: 40 }}>
            Loading supply pipeline…
          </div>
        ) : data && data.status !== "ok" ? (
          <div className="empty" style={{ padding: 40 }}>
            <div style={{ fontWeight: 600, color: "var(--ink-2)", marginBottom: 4 }}>Supply pipeline not available</div>
            <div style={{ fontSize: 12.5 }}>{data.detail || "Connection is not configured yet."}</div>
          </div>
        ) : items.length === 0 ? (
          <div className="empty" style={{ padding: 40 }}>
            {all.length === 0
              ? "No pipeline units in the tracked stages right now."
              : "No units match the current search / filters."}
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                {isAdmin && <SortTh label="UID" sortKey="uid" activeKey={sortKey} dir={dir} onSort={onSort} />}
                <SortTh label="Society" sortKey="society" activeKey={sortKey} dir={dir} onSort={onSort} />
                <SortTh label="Locality" sortKey="locality" activeKey={sortKey} dir={dir} onSort={onSort} />
                <SortTh label="City" sortKey="city" activeKey={sortKey} dir={dir} onSort={onSort} />
                <SortTh label="Config" sortKey="config" activeKey={sortKey} dir={dir} onSort={onSort} />
                <SortTh label="Area" sortKey="area" activeKey={sortKey} dir={dir} onSort={onSort} />
                <th>Tower / Unit</th>
                {isAdmin && (
                  <SortTh label="Demand Price" sortKey="price" activeKey={sortKey} dir={dir} onSort={onSort} />
                )}
                <SortTh label="Stage" sortKey="stage" activeKey={sortKey} dir={dir} onSort={onSort} />
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id}>
                  {isAdmin && <td style={{ fontFamily: "'Spline Sans Mono'", fontSize: 12 }}>{s.id}</td>}
                  <td style={{ fontWeight: 600 }}>{s.society || "—"}</td>
                  <td style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{s.locality || "—"}</td>
                  <td style={{ fontSize: 12.5 }}>{s.city || "—"}</td>
                  <td>{s.configuration ? <span className="cfg-chip">{s.configuration}</span> : "—"}</td>
                  <td style={{ fontSize: 12.5 }}>
                    {s.area_sqft != null ? `${s.area_sqft.toLocaleString("en-IN")} sq.ft` : "—"}
                  </td>
                  <td style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{unitText(s, isAdmin)}</td>
                  {isAdmin && <td style={{ fontWeight: 600 }}>{formatPrice(s.price_lacs, s.price_text)}</td>}
                  <td>
                    <span className={`sup-stage ${s.stage_key}`}>{s.stage}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
