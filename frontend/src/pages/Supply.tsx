/* Supply Pipeline — table with topbar search, stage filter pills, and city/config filters. */
import { useState } from "react";
import { useSupply, formatPrice } from "../lib/queries";
import { SupplyItem } from "../lib/api";
import { matches } from "../components/SearchContext";
import { uniqueValues, inBudget } from "../components/Filters";
import { useSort, SortTh } from "../lib/useSort";
import { useAuth } from "../components/AuthContext";
import { FilterBar, useFilterValues } from "../components/FilterBar";

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
        <span className="cfg-chip" style={{ background: "var(--slate-soft)", color: "var(--slate)", fontSize: 9.5, fontFamily: "var(--font-mono)" }}>
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
  // Local, now that the topbar no longer carries a global box.
  const [query, setQuery] = useState("");
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  const { values: f, set, clear } = useFilterValues({
    city: "", config: "", budget: { min: "", max: "" },
  });
  const { city, config } = f;
  const budMin = f.budget.min, budMax = f.budget.max;

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
        <div className="field" style={{ marginBottom: 0, minWidth: 260, flex: 1, maxWidth: 420 }}>
          <input value={query} onChange={(e) => setQuery(e.target.value)}
                 placeholder="Search society, locality, city, config, stage" />
        </div>
        <FilterBar
          fields={[
            { key: "city", label: "City", options: uniqueValues(all, (s) => s.city) },
            { key: "config", label: "Config", options: uniqueValues(all, (s) => s.configuration) },
            { key: "budget", label: "Budget (₹ L)", kind: "range", hidden: !isAdmin },
          ]}
          values={f} onChange={set} onClear={clear}
        />
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
                  {isAdmin && <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{s.id}</td>}
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
