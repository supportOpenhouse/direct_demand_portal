/* Inventory Snapshot — pure helpers.
   Ported from the Demand CRM's SnapshotView.jsx so the rebuilt page derives every
   field identically. React lives in pages/Inventory.tsx; nothing here touches it.

   The two apps read the SAME inventory sheet: DDP's sync keeps the whole row in
   inventory_units.raw (see backend/app/services/inventory_sync.py), so the CRM's
   sheet-native fields — micro_market, locality_or_sector, sales_manager, home_id,
   super_sqft — are already on the wire. The accessors below prefer the projected
   column where the backend normalises it (city, configuration) and fall back to raw
   otherwise. */
import type { InventoryItem } from "./api";

export const CITY_ORDER = ["Gurgaon", "Noida", "Ghaziabad"];

export const CITY_CFG: Record<string, { sub: string }> = {
  Gurgaon: { sub: "Openhouse · Gurgaon Inventory" },
  Noida: { sub: "Openhouse · Noida Inventory" },
  Ghaziabad: { sub: "Openhouse · Ghaziabad Inventory" },
};

export const citySub = (city: string) =>
  (CITY_CFG[city] || { sub: `Openhouse · ${city} Inventory` }).sub;

/* ── raw access ─────────────────────────────────────────────────────────────── */

/** A trimmed string out of the sheet row, or "" — `raw` is Record<string, unknown>,
    and a numeric cell can arrive as a number. */
export function rawStr(p: InventoryItem, key: string): string {
  const v = (p.raw as Record<string, unknown> | null | undefined)?.[key];
  if (v == null) return "";
  return String(v).trim();
}

const or = (...xs: (string | null | undefined)[]) => xs.find((x) => x && x.trim())?.trim() || "";

export const societyOf = (p: InventoryItem) => or(rawStr(p, "society_name"), p.society);
export const propertyNameOf = (p: InventoryItem) => or(rawStr(p, "property_name"), p.name);
/** normalize_city() already folds "Greater Noida"/"Gurugram" into the CITY_ORDER
    names, so the projected column wins over the sheet's own text. */
export const cityOf = (p: InventoryItem) => or(p.city, rawStr(p, "city_name"));
export const microMarketOf = (p: InventoryItem) => or(rawStr(p, "micro_market"), p.locality);
export const localityOf = (p: InventoryItem) =>
  or(rawStr(p, "locality_or_sector"), p.locality, rawStr(p, "micro_market"));
export const configOf = (p: InventoryItem) => or(p.configuration, rawStr(p, "configuration"));
export const pmOf = (p: InventoryItem) => rawStr(p, "sales_manager");
export const homeIdOf = (p: InventoryItem) => rawStr(p, "home_id");

/** The sheet's own super_sqft text first ("1,450"), so the page reads like the sheet;
    the parsed numeric column is the fallback. */
export function sqftOf(p: InventoryItem): string {
  const raw = rawStr(p, "super_sqft");
  if (raw) return raw;
  return p.area_sqft != null ? p.area_sqft.toLocaleString("en-IN") : "";
}

/** Strip the society prefix off the full property name, then trim any leading AND
    trailing space/comma/dash — property_name is "{unit}, {society}", so removing the
    society leaves a trailing comma that has to go too. */
export function unitOf(p: InventoryItem): string {
  const full = propertyNameOf(p);
  const soc = societyOf(p);
  return (
    (soc ? full.replace(soc, "") : full)
      .replace(/^[ ,\-]+/, "")
      .replace(/[ ,\-]+$/, "") || "—"
  );
}

/* ── status ─────────────────────────────────────────────────────────────────── */

/* `status` off /v1/inventory is already "live demand_details.availability_status
   where the supply_form_uid matched, else the sheet's listing_status" (see
   backend/app/services/availability.py). One field, two vocabularies — so classify by
   keyword rather than by equality, and both Ready/Coming Soon and
   Available/Booked/Sold/Dead bucket correctly. */
export type StatusKind = "r" | "cs" | "bk" | "sd" | "dd" | "na";

export const statusOf = (p: InventoryItem) => (p.status || "").trim();

export function statusKind(s: string | null | undefined): StatusKind {
  const v = (s || "").toLowerCase();
  if (v.includes("available") || v.includes("ready")) return "r";
  if (v.includes("coming")) return "cs";
  if (v.includes("booked")) return "bk";
  if (v.includes("sold")) return "sd";
  if (v.includes("dead") || v.includes("archived")) return "dd";
  return "na";
}

const RANK: Record<StatusKind, number> = { r: 0, cs: 1, bk: 2, sd: 3, dd: 4, na: 5 };
export const statusRank = (s: string | null | undefined) => RANK[statusKind(s)];

/** Statuses that still represent stock worth sharing — the default filter. Mirrors the
    CRM's ['Coming Soon','Ready','Booked'], in whatever vocabulary the data holds. */
export const SELLABLE_KINDS: StatusKind[] = ["r", "cs", "bk"];
export const isSellable = (s: string | null | undefined) =>
  SELLABLE_KINDS.includes(statusKind(s));

/** The NEW badge — a unit the sheet still calls Coming Soon (legacy isPropertyNew). */
export const isNew = (p: InventoryItem) => statusKind(statusOf(p)) === "cs";

/* ── price ──────────────────────────────────────────────────────────────────── */

/** "1.2 Cr" / "85 L" / "9500000" → rupees. Ported from the CRM's legacy parsePrice,
    used only when the backend could not parse price_lacs. */
export function parsePriceText(s: string | null | undefined): number {
  if (!s) return 0;
  const m = String(s).match(/([\d.]+)\s*(L|Cr|K)?/i);
  if (!m) return 0;
  const n = parseFloat(m[1]) || 0;
  const u = (m[2] || "").toUpperCase();
  return u === "CR" ? n * 1e7 : u === "K" ? n * 1e3 : u === "L" ? n * 1e5 : n;
}

/** Rupees → "₹1.2 Cr" / "₹85 L". The CRM's fmtPrice, verbatim. */
export function fmtRupees(p: number): string {
  if (!p) return "—";
  if (p >= 1e7) return "₹" + (p / 1e7).toFixed(p % 1e7 === 0 ? 0 : 2) + " Cr";
  if (p >= 1e5) return "₹" + (p / 1e5).toFixed(p % 1e5 === 0 ? 0 : 2) + " L";
  return "₹" + Math.round(p).toLocaleString("en-IN");
}

/** Lacs — the unit the backend already parsed into. Falls back to the price text so a
    row the parser choked on still answers a budget filter rather than dropping out. */
export function priceLacsOf(p: InventoryItem): number | null {
  if (p.price_lacs != null) return p.price_lacs;
  const rs = parsePriceText(p.price_text);
  return rs > 0 ? rs / 1e5 : null;
}

/** Ask price as it should read on the row: the sheet's own text wins (it is what
    supply typed), then the parsed value. */
export const priceTextOf = (p: InventoryItem) =>
  or(p.price_text, rawStr(p, "listing_price")) ||
  (p.price_lacs != null ? fmtRupees(p.price_lacs * 1e5) : "—");

/** Active price range → a title fragment: "₹1.5 Cr–₹2 Cr" / "≤₹2 Cr" / "₹1.5 Cr+".
    Inputs are in CRORES, the natural unit for these listings. */
export function priceLabel(minCr: number | null, maxCr: number | null): string | null {
  const lo = minCr != null ? fmtRupees(minCr * 1e7) : null;
  const hi = maxCr != null ? fmtRupees(maxCr * 1e7) : null;
  if (lo && hi) return `${lo}–${hi}`;
  if (hi) return `≤${hi}`;
  if (lo) return `${lo}+`;
  return null;
}

/* ── dates ──────────────────────────────────────────────────────────────────── */

export const TODAY = new Date();

const pad2 = (n: number) => String(n).padStart(2, "0");

/** yyyy-mm-dd, for the export filename. */
export const ymd = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

/** dd/mm/yyyy — built by hand, never toLocale*. The poster and the share text are
    read on whatever machine opens them, and locale formatters let the OS pick
    day-vs-month order, which showed mm/dd on Windows and dd/mm on Mac. */
export const fmtDate = (d: Date) => `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`;

/* ── grouping ───────────────────────────────────────────────────────────────── */

export interface CityGroup {
  mmGroups: Record<string, InventoryItem[]>;
  ordered: string[];
  total: number;
}

/** The cities present in `items`: the three fixed ones in order, then anything else
    alpha. normalize_city() also emits Faridabad/Delhi/other, and the CRM — which only
    ever saw three — would have dropped them off the page while still counting them.
    Listing the extras keeps the body honest with the count, and matches what the text
    and image exports already do. */
export function citiesOf(items: InventoryItem[]): string[] {
  const present = new Set(items.map(cityOf).filter(Boolean));
  const out = CITY_ORDER.filter((c) => present.has(c));
  [...present].sort().forEach((c) => {
    if (!out.includes(c)) out.push(c);
  });
  return out;
}

/** city → { micro-market groups, alpha micro-market order, unit count }.
    Societies are sorted alpha within each micro-market. */
export function groupPropertiesByCity(items: InventoryItem[]): Record<string, CityGroup> {
  const result: Record<string, CityGroup> = {};
  citiesOf(items).forEach((city) => {
    const props = items.filter((p) => cityOf(p) === city);
    const mmGroups: Record<string, InventoryItem[]> = {};
    props.forEach((p) => {
      const k = microMarketOf(p) || "Other";
      (mmGroups[k] = mmGroups[k] || []).push(p);
    });
    Object.keys(mmGroups).forEach((k) => {
      mmGroups[k].sort((a, b) => societyOf(a).localeCompare(societyOf(b)));
    });
    result[city] = { mmGroups, ordered: Object.keys(mmGroups).sort(), total: props.length };
  });
  return result;
}

/* ── share text ─────────────────────────────────────────────────────────────── */

const DOT: Record<StatusKind, string> = {
  r: "🟢",
  cs: "🟡",
  bk: "🔵",
  sd: "⚪",
  dd: "⚪",
  na: "⚪",
};

/** A WhatsApp-ready block for any unit list, grouped city → micro-market. */
export function buildShareText(items: InventoryItem[], headline: string, senderName?: string | null): string {
  let body = `🏠 *${headline}*\nUpdated ${fmtDate(TODAY)}\n\n`;
  citiesOf(items).forEach((c) => {
    /* micro-market, then society — the CRM sorted on micro-market alone, which left
       societies interleaved in the share while the table and the poster both grouped
       them. Same list, same grouping, so it should read in the same order. */
    const cityProps = items
      .filter((p) => cityOf(p) === c)
      .sort(
        (a, b) =>
          microMarketOf(a).localeCompare(microMarketOf(b)) ||
          societyOf(a).localeCompare(societyOf(b)) ||
          unitOf(a).localeCompare(unitOf(b)),
      );
    if (!cityProps.length) return;
    body += `━━━ ${(c || "Other").toUpperCase()} (${cityProps.length} units) ━━━\n\n`;
    let lastMM = "";
    cityProps.forEach((p) => {
      const mm = microMarketOf(p) || "Other";
      if (mm !== lastMM) {
        if (lastMM) body += "\n";
        body += `*${mm}*\n`;
        lastMM = mm;
      }
      const u = unitOf(p);
      const unit = u === "—" ? "" : u;
      const loc = localityOf(p);
      const st = statusOf(p);
      const kind = statusKind(st);
      const sqft = sqftOf(p);
      body +=
        `${DOT[kind]} ${societyOf(p) || "—"}${unit ? ` ${unit}` : ""}${loc ? ` · ${loc}` : ""}` +
        ` · ${configOf(p)} · ${sqft ? `${sqft} sqft` : "—"} · ${priceTextOf(p)}` +
        `${kind !== "r" && st ? ` (${st})` : ""}\n`;
    });
    body += "\n";
  });
  const first = (senderName || "").trim() || "Team";
  body += `\nReach out for site visits, virtual tour, or pricing details.\n\n– ${first}, Openhouse`;
  return body;
}
