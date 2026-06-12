/* Live Inventory — prototype invCard() grid with real photos (joined on home_id),
   topbar search and city/config/status filters. */
import { useState } from "react";
import { useInventory, useSyncInventory, formatPrice } from "../lib/queries";
import { InventoryItem } from "../lib/api";
import { useToast } from "../components/Toast";
import { useSearch, matches } from "../components/SearchContext";
import { FilterSelect, uniqueValues } from "../components/Filters";

function fmtArea(a: number | null): string | null {
  if (a == null) return null;
  return `${a.toLocaleString("en-IN")} sq.ft`;
}

function InvCard({ p }: { p: InventoryItem }) {
  const toast = useToast();
  const name = p.name || p.society || "—";
  const loc = [p.locality, p.city].filter(Boolean).join(", ") || "—";
  const photoCount = (() => {
    try {
      const imgs = p.raw.images;
      return Array.isArray(imgs) ? imgs.length : 0;
    } catch {
      return 0;
    }
  })();
  return (
    <div className="inv-card">
      <div
        className="inv-img"
        style={
          p.image_url
            ? { backgroundImage: `url('${p.image_url}')` }
            : { background: "linear-gradient(135deg,#e4e9f1,#d3dbe8)", display: "grid", placeItems: "center" }
        }
      >
        {!p.image_url && <span style={{ fontSize: 28, opacity: 0.45 }}>🏠</span>}
        {p.status && <span className="tag">{p.status}</span>}
        {photoCount > 1 && (
          <span className="tag" style={{ right: 9, left: "auto", top: 9 }}>
            📷 {photoCount}
          </span>
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
          <button className="btn wa sm" style={{ flex: 1 }} onClick={() => toast(`Brochure for ${name} sent on WhatsApp`, "wa", "↗")}>
            ↗ Share brochure
          </button>
          <button className="btn ghost sm" onClick={() => toast(`Opening ${name} details`, "blue", "🏠")}>
            Details
          </button>
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
  const items = all.filter(
    (p) =>
      (!city || p.city === city) &&
      (!config || p.configuration === config) &&
      (!status || p.status === status) &&
      matches(query, p.name, p.society, p.locality, p.city, p.configuration, p.status)
  );
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
