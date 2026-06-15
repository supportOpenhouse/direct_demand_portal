/* Live Inventory — prototype invCard() grid with real photos (joined on home_id),
   topbar search and city/config/status filters. */
import { useState } from "react";
import { useInventory, useSyncInventory, formatPrice } from "../lib/queries";
import { InventoryItem } from "../lib/api";
import { useToast } from "../components/Toast";
import { useSearch, matches } from "../components/SearchContext";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { useSort } from "../lib/useSort";
import { waShare } from "../lib/whatsapp";

function fmtArea(a: number | null): string | null {
  if (a == null) return null;
  return `${a.toLocaleString("en-IN")} sq.ft`;
}

function imagesOf(p: InventoryItem): string[] {
  const imgs = (p.raw as any)?.images;
  if (Array.isArray(imgs) && imgs.length) return imgs.filter(Boolean);
  return p.image_url ? [p.image_url] : [];
}

function InvCard({ p }: { p: InventoryItem }) {
  const toast = useToast();
  const name = p.name || p.society || "—";
  const loc = [p.locality, p.city].filter(Boolean).join(", ") || "—";
  const imgs = imagesOf(p);
  const [idx, setIdx] = useState(0);
  const cur = imgs[idx];
  const go = (e: React.MouseEvent, d: number) => {
    e.stopPropagation();
    setIdx((i) => (i + d + imgs.length) % imgs.length);
  };

  const share = () => {
    const text = `🏠 ${name}\n📍 ${loc}\n${formatPrice(p.price_lacs, p.price_text)} · ${p.configuration || ""} ${fmtArea(p.area_sqft) || ""}`.trim()
      + (cur ? `\n${cur}` : "");
    waShare(text);
  };

  return (
    <div className="inv-card">
      <div
        className="inv-img"
        style={cur
          ? { backgroundImage: `url('${cur}')` }
          : { background: "linear-gradient(135deg,#e4e9f1,#d3dbe8)", display: "grid", placeItems: "center" }}
      >
        {!cur && <span style={{ fontSize: 28, opacity: 0.45 }}>🏠</span>}
        {p.status && <span className="tag">{p.status}</span>}
        {imgs.length > 1 && (
          <>
            <button className="carousel-btn" style={{ left: 8 }} title="Previous photo" onClick={(e) => go(e, -1)}>‹</button>
            <button className="carousel-btn" style={{ right: 8 }} title="Next photo" onClick={(e) => go(e, 1)}>›</button>
            <div style={{ position: "absolute", bottom: 8, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 4 }}>
              {imgs.map((_, i) => (
                <span key={i} style={{ width: 5, height: 5, borderRadius: "50%", background: i === idx ? "#fff" : "rgba(255,255,255,.5)" }} />
              ))}
            </div>
            <span className="tag" style={{ right: 9, left: "auto", top: 9 }}>📷 {idx + 1}/{imgs.length}</span>
          </>
        )}
      </div>
      <div className="inv-body">
        <div className="nm">{name}</div>
        <div className="loc">📍 {loc}</div>
        <div className="pr">{formatPrice(p.price_lacs, p.price_text)}</div>
        <div className="inv-meta">
          {p.configuration && <span>{p.configuration}</span>}
          {fmtArea(p.area_sqft) && <span>{fmtArea(p.area_sqft)}</span>}
          {p.city && <span>{p.city}</span>}
        </div>
        <div className="inv-actions">
          <button className="btn wa sm" style={{ flex: 1 }} onClick={share}>↗ Share brochure</button>
          <button className="btn ghost sm" onClick={() => toast(`Opening ${name} details`, "blue", "🏠")}>Details</button>
        </div>
      </div>
    </div>
  );
}

export default function Inventory() {
  const { data, isLoading } = useInventory();
  const sync = useSyncInventory();
  const toast = useToast();
  const { query } = useSearch();
  const [city, setCity] = useState("");
  const [config, setConfig] = useState("");
  const [status, setStatus] = useState("");

  const all = data?.items ?? [];
  const matched = all.filter(
    (p) =>
      (!city || p.city === city) &&
      (!config || p.configuration === config) &&
      (!status || p.status === status) &&
      matches(query, p.name, p.society, p.locality, p.city, p.configuration, p.status)
  );
  // a card grid has no column headers — drive the shared sort hook from a dropdown
  const { sorted: items, sortKey, dir, onSort } = useSort<InventoryItem>(matched, {
    name: (p) => p.name,
    society: (p) => p.society,
    city: (p) => p.city,
    config: (p) => p.configuration,
    area: (p) => p.area_sqft,
    price: (p) => p.price_lacs,
    status: (p) => p.status,
  });
  const filtered = items.length !== all.length;

  const synced = data?.last_synced_at
    ? new Date(data.last_synced_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })
    : null;

  return (
    <>
      <div className="section-head">
        <p className="sec-sub" style={{ margin: 0 }}>
          Live inventory — synced from the Acquired Property sheet.
          {synced && (
            <>
              {" "}
              Last synced <b style={{ color: "var(--ink-2)" }}>{synced}</b> ·{" "}
              <b style={{ color: "var(--ink-2)" }}>
                {filtered ? `${items.length} of ${all.length}` : all.length} units
              </b>
            </>
          )}
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <FilterSelect label="City" value={city} options={uniqueValues(all, (p) => p.city)} onChange={setCity} width={130} />
          <FilterSelect label="Config" value={config} options={uniqueValues(all, (p) => p.configuration)} onChange={setConfig} width={130} />
          <FilterSelect label="Status" value={status} options={uniqueValues(all, (p) => p.status)} onChange={setStatus} width={140} />
          <div className="field" style={{ marginBottom: 0, width: 150 }}>
            <select
              value={sortKey || ""}
              onChange={(e) => e.target.value && onSort(e.target.value)}
              style={{ padding: "7px 10px", fontSize: 12.5 }}
            >
              <option value="">Sort: default</option>
              <option value="price">Sort: Price</option>
              <option value="area">Sort: Area</option>
              <option value="society">Sort: Society</option>
              <option value="city">Sort: City</option>
              <option value="status">Sort: Status</option>
            </select>
          </div>
          {sortKey && (
            <button className="btn ghost sm" title="Toggle direction" onClick={() => onSort(sortKey)}>
              {dir === "asc" ? "↑" : "↓"}
            </button>
          )}
          {(city || config || status || query) && (
            <button
              className="btn ghost sm"
              onClick={() => {
                setCity("");
                setConfig("");
                setStatus("");
              }}
            >
              Clear
            </button>
          )}
          <button
            className="btn ghost sm"
            disabled={sync.isPending}
            onClick={() =>
              sync.mutate(undefined, {
                onSuccess: (r) => toast(`Inventory synced · ${r.rows} units`, "green", "⟳"),
                onError: (e) => toast(e.message, "gold", "⚠"),
              })
            }
          >
            {sync.isPending ? "Syncing…" : "⟳ Sync now"}
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="card">
          <div className="empty" style={{ padding: 40 }}>
            Loading inventory…
          </div>
        </div>
      ) : data && data.status !== "ok" ? (
        <div className="card">
          <div className="empty" style={{ padding: 40 }}>
            <div style={{ fontWeight: 600, color: "var(--ink-2)", marginBottom: 4 }}>Inventory not available</div>
            <div style={{ fontSize: 12.5 }}>{data.detail || "Sync is not configured yet."}</div>
          </div>
        </div>
      ) : items.length === 0 ? (
        <div className="card">
          <div className="empty" style={{ padding: 40 }}>
            {all.length === 0 ? "No units in the sheet yet." : "No units match the current search / filters."}
          </div>
        </div>
      ) : (
        <div className="grid cards-3">
          {items.map((p) => (
            <InvCard key={p.id} p={p} />
          ))}
        </div>
      )}
    </>
  );
}
