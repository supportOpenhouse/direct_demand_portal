/* Supply Pipeline — table with topbar search, stage filter pills, and city/config filters. */
import { useState } from "react";
import { useSupply, formatPrice } from "../lib/queries";
import { SupplyItem } from "../lib/api";
import { useSearch, matches } from "../components/SearchContext";
import { FilterSelect, uniqueValues, BudgetRange, inBudget } from "../components/Filters";
import { useSort, SortTh } from "../lib/useSort";
import { useAuth } from "../components/AuthContext";

/* active pipeline — live cp_inventory_status.supply_status (dead/rejected/cancelled
   hidden); closest-to-landing first. Future Prospect = Hold + Price High + Future Prospect */
const STAGE_ORDER = ["AMA Signed", "Token Transferred", "Token Requested", "AMA Req", "Negotiation", "Visit Completed", "Visit Scheduled", "Followup", "Listed", "Key Handover", "Future Prospect"];

/* OH reference price matched by society + area (±5). Confident match → green ₹;
   otherwise "Check Price" (brown) with a reason chip + hover tooltip. */
function PriceCell({ s }: { s: SupplyItem }) {
  if (!s.price_status) {  // pricing DB unavailable → fall back to the demand price
    return <span style={{ fontWeight: 600 }}>{formatPrice(s.price_lacs, s.price_text)}</span>;
  }
  if (s.price_status === "match") {
    return (
      <span style={{ fontWeight: 700, color: "var(--emerald)" }} title={s.price_tooltip || ""}>
        {formatPrice(s.oh_price_lacs, null)}
      </span>
    );
  }
  return (
    <div title={s.price_tooltip || ""} style={{ cursor: "help", lineHeight: 1.35 }}>
      <div style={{ fontWeight: 700, color: "var(--gold)" }}>Check Price</div>
      {s.price_reason && (
        <span className="cfg-chip" style={{ background: "var(--slate-soft)", color: "var(--slate)", fontSize: 9.5, fontFamily: "'Spline Sans Mono'" }}>
          {s.price_reason}
        </span>
      )}
    </div>
  );
}

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
  const [city, setCity] = useState("");
  const [config, setConfig] = useState("");
  const [budMin, setBudMin] = useState("");
  const [budMax, setBudMax] = useState("");

  const all = data?.items ?? [];
  const base = all
    .filter(
      (s) =>
        (!city || s.city === city) &&
        (!config || s.configuration === config) &&
        inBudget(s.oh_price_lacs, budMin, budMax) &&
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
    price: (s) => s.oh_price_lacs,
  });

  return (
    <>
      <div className="section-head">
        <div />
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <FilterSelect label="City" value={city} options={uniqueValues(all, (s) => s.city)} onChange={setCity} width={130} />
          <FilterSelect label="Config" value={config} options={uniqueValues(all, (s) => s.configuration)} onChange={setConfig} width={130} />
          {isAdmin && <BudgetRange min={budMin} max={budMax} onMin={setBudMin} onMax={setBudMax} />}
          {(city || config || budMin || budMax) && (
            <button
              className="btn ghost sm"
              onClick={() => {
                setCity("");
                setConfig("");
                setBudMin("");
                setBudMax("");
              }}
            >
              Clear
            </button>
          )}
        </div>
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
          <div className="table-wrap">
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
                  <SortTh label="OH Price" sortKey="price" activeKey={sortKey} dir={dir} onSort={onSort} />
                )}
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
                  {isAdmin && <td><PriceCell s={s} /></td>}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </>
  );
}
