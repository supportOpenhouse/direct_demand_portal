/* Demand Dashboard — the supply team's property book, rebuilt here READ-ONLY.

   A port of github.com/oh/Demand-Dashboard's list screen: same rows, same columns, our
   table, our filters, our type scale. Nothing on this page writes — that app owns these
   properties and is the only thing that edits them, for any role.

   Their screen expands a panel BELOW the clicked row. Here a row opens the popup, like
   every lead row does, so the five sections get the modal's own motion and a stack-aware
   Escape instead of a second animation nobody else in this app uses. */
import { Fragment, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useDemandProperties } from "../lib/queries";
import { DemandProperty } from "../lib/api";
import { FilterBar, useFilterValues } from "../components/FilterBar";
import { countedOptions, matchesOption } from "../components/Filters";
import SlideTabs from "../components/SlideTabs";
import { MultiSelect } from "../components/MultiSelect";
/* No Invalid City tab: `city` is NOT NULL-in-practice here — all 398 rows are one of
   the three (checked on prod). Unlike leads, these come from the supply form, not a
   sheet, so there is no #N/A row to make reachable. */
import { CITY_TABS, cityMatches } from "../components/LeadToolbar";
import { Pager, usePaging } from "../components/Pager";
import { StageBoxes } from "../components/StageBoxes";
import { SkeletonTable } from "../components/Skeleton";
import { useSort, SortTh } from "../lib/useSort";
import { useModalExit } from "../lib/useModalExit";
import { useLeadColumns } from "../features/leadTable/ColumnSettings";
import { TopbarSlot } from "../components/TopbarSlot";
import { IconPlay, IconSearch, IconX } from "../components/icons";

/* ₹ in lakh, as the source dashboard prints it. A price is a real (float) column there,
   so 170 means ₹1.70 Cr — shown in lakh because that is the unit the team speaks in. */
const money = (v: unknown): string =>
  v === null || v === undefined || v === "" ? "—" : `₹${Number(v).toLocaleString("en-IN")} L`;

/* Five columns are JSONB lists (extra_area, furnishing_details, documents_available,
   additional_images are lists of strings; balcony_details is a list of objects). A bare
   String() on those prints "[object Object],[object Object]", which is what this page
   shipped with — so `text` handles a list itself rather than trusting every call site. */
const text = (v: unknown): string => {
  if (Array.isArray(v)) return v.length ? v.map(text).join(" · ") : "—";
  if (v && typeof v === "object") {
    const parts = Object.entries(v as Record<string, unknown>)
      .filter(([k, x]) => x !== null && x !== "" && !k.endsWith("_image"))
      .map(([, x]) => String(x));
    return parts.length ? parts.join(" · ") : "—";
  }
  const s = v === null || v === undefined ? "" : String(v).trim();
  return s === "" ? "—" : s;
};

/* One line per balcony, in the order the supply form captured them: which room it is
   attached to, which way it faces, what it looks onto — one balcony per line.

   Each balcony carries two Cloudinary URLs — `view_image` (what it looks onto) and
   `compass_image` (the facing shot). The LINE is the link to the view photo, with a
   separate "compass" link after it, so 1,032 balconies don't become 2,064 bare URLs.
   A balcony with no photo renders as plain text rather than a dead link. */
const balconies = (v: unknown): ReactNode => {
  if (!Array.isArray(v) || !v.length) return "—";
  const rows = v.map((b, i) => {
    const o = (b ?? {}) as Record<string, unknown>;
    const url = (k: string) =>
      typeof o[k] === "string" && (o[k] as string).startsWith("http") ? (o[k] as string) : null;
    return {
      key: `${i}`,
      n: o.index ? `#${o.index}` : `#${i + 1}`,
      room: o.attached_to ? String(o.attached_to) : "",
      facing: o.facing ? `${o.facing} facing` : "",
      view: o.view ? `${o.view} view` : "",
      viewImg: url("view_image"),
      compass: url("compass_image"),
    };
  });
  if (!rows.length) return "—";
  /* A GRID, not a run of text: the four parts line up down the list, so you read a
     column of rooms and a column of facings rather than re-finding them on each line.
     The row is one link (`display:contents` keeps its cells as grid items). */
  return (
    <div className="dd-balcs">
      {rows.map((r) => (
        <Fragment key={r.key}>
          {r.viewImg ? (
            <a className="dd-balc" href={r.viewImg} target="_blank" rel="noreferrer"
               title="Open the balcony photo in a new tab">
              <span>{r.n}</span><span>{r.room}</span><span>{r.facing}</span><span>{r.view}</span>
            </a>
          ) : (
            <span className="dd-balc dd-balc-plain">
              <span>{r.n}</span><span>{r.room}</span><span>{r.facing}</span><span>{r.view}</span>
            </span>
          )}
          {r.compass
            ? <a className="dd-compass" href={r.compass} target="_blank" rel="noreferrer"
                 title="Open the compass photo in a new tab">compass</a>
            : <span />}
        </Fragment>
      ))}
    </div>
  );
};

/* Dates arrive as ISO from Postgres DATE columns. Their dashboard prints d MMM yyyy. */
const day = (v: unknown): string => {
  if (!v) return "—";
  const d = new Date(String(v));
  return isNaN(d.getTime()) ? String(v)
    : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
};

const num = (v: unknown): string =>
  v === null || v === undefined || v === "" ? "—" : Number(v).toLocaleString("en-IN");

/* Availability is the pill on the row: Available / Booked / Sold. (Dead is a soft delete
   and never leaves the backend.) The hues are ours, not theirs — this page has to read
   like the rest of the portal. */
const AVAIL_CLASS: Record<string, string> = {
  Available: "won", Booked: "contacted", Sold: "new",
};

function unitLine(p: DemandProperty): string {
  const bits = [
    p.tower_no?.trim() && `Tower ${p.tower_no.trim()}`,
    p.unit_no?.trim() && `Unit ${p.unit_no.trim()}`,
    p.floor?.trim() && `Floor ${p.floor.trim()}`,
  ].filter(Boolean);
  return bits.length ? bits.join(" · ") : "—";
}

/* The popup's sections. Theirs are Property · Society & Charges · Possession & Listing ·
   Owner & Loan · Media; ours drop the fields the demand team doesn't work from — the
   seller's identity and contact, and the demand pipeline (its dates are the supply app's
   own workflow, and availability is already the chip in the header).
   Each entry is [label, column]; a column
   the row doesn't carry renders "—" rather than vanishing, so the shape is stable
   between two properties. */
/* Fields that take the whole row rather than one grid track — the long ones, which in a
   260px column wrap into five lines while the column beside them sits empty. Balcony
   details is one line per balcony; furnishing is a long single run of items. */
const WIDE = new Set(["balcony_details", "furnishing_details"]);

const SECTIONS: { title: string; fields: [string, string, ((v: unknown) => ReactNode)?][] }[] = [
  {
    title: "Property",
    fields: [
      ["UID", "uid"], ["Society", "society_name"], ["Tower", "tower_no"], ["Unit", "unit_no"],
      ["Floor", "floor"], ["City", "city"], ["Locality", "locality"], ["Micro-market", "micro_market"],
      ["Configuration", "configuration"], ["Area (sqft)", "area_sqft", num],
      ["Super area", "super_area", num], ["Carpet area", "carpet_area", num],
      ["Extra area", "extra_area", num], ["Bathrooms", "bathrooms"], ["Balconies", "balconies"],
      ["Supply status", "supply_status"], ["Exit facing", "exit_facing"],
      ["POC", "poc"], ["Balcony details", "balcony_details", balconies],
    ],
  },
  {
    title: "Society & charges",
    fields: [
      ["Total lifts", "total_lifts"], ["Floors in tower", "total_floors_tower"],
      ["Flats per floor", "total_flats_floor"], ["Society age (yrs)", "society_age_years"],
      ["Total units", "total_units"], ["Maintenance", "maintenance_charges"],
      ["Move-in charges", "society_move_in_charges"], ["Electricity", "electricity_charges"],
      ["DG charges", "dg_charges"], ["Circle rate", "circle_rate"],
      ["Gas pipeline", "gas_pipeline"], ["Club facility", "club_facility"],
      ["Parking", "parking"], ["Parking number", "parking_number"],
      ["Property tax status", "property_tax_status"],
    ],
  },
  {
    title: "Possession & listing",
    fields: [
      ["Possession", "possession_status"], ["Occupancy", "occupancy_status"],
      ["Current occupancy %", "current_occupancy_pct"],
      ["Key handover", "key_handover_date", day], ["Tentative handover", "tentative_handover_date", day],
      ["AMA date", "ama_date", day], ["AMA payment structure", "ama_payment_structure"],
      ["Alpha / beta", "alpha_beta"], ["Beta %", "beta_pct"],
      ["Beta min %", "ama_beta_min_pct"], ["Beta max %", "ama_beta_max_pct"],
      ["Listing asking price", "listing_asking_price", money],
      ["Demand price", "demand_price", money], ["Listing price", "listing_price", money],
      ["Furnishing", "furnishing"], ["Furnishing details", "furnishing_details"],
    ],
  },
  {
    title: "Loan & documents",
    fields: [
      ["Outstanding loan", "outstanding_loan"], ["Bank", "bank_name_loan"],
      ["Documents available", "documents_available"],
    ],
  },
];

/* The table's columns, defined ONCE: header, cell and sort accessor together. The
   Columns button (shared with the lead tables) reorders and hides them, stored per
   browser under `dd_cols:demand-dashboard`. To add a column, add an entry here.
   `DEMAND_COLS` is the ORIGINAL layout — their ten, in their order — so Reset returns
   to the page as shipped. */
type DDColumn = {
  id: string;
  label: string;
  tight?: boolean;
  cell: (p: DemandProperty) => ReactNode;
  sort?: (p: DemandProperty) => string | number;
};

export const DEMAND_COLUMNS: DDColumn[] = [
  { id: "society", label: "Society / Unit",
    cell: (p) => (<><div className="who"><b>{text(p.society_name)}</b></div>
                   <div className="sub">{unitLine(p)}</div></>),
    sort: (p) => (p.society_name ?? "").toLowerCase() },
  { id: "city", label: "City", tight: true, cell: (p) => text(p.city),
    sort: (p) => (p.city ?? "").toLowerCase() },
  { id: "locality", label: "Locality", cell: (p) => text(p.locality ?? p.micro_market),
    sort: (p) => (p.locality ?? p.micro_market ?? "").toLowerCase() },
  { id: "config", label: "Config", tight: true, cell: (p) => text(p.configuration),
    sort: (p) => String(p.configuration ?? "") },
  { id: "area", label: "Size (sqft)", tight: true, cell: (p) => num(p.area_sqft),
    sort: (p) => p.area_sqft ?? 0 },
  { id: "price", label: "Listing Price", tight: true, cell: (p) => <b>{money(p.listing_price)}</b>,
    sort: (p) => p.listing_price ?? 0 },
  { id: "ama", label: "AMA Date", tight: true, cell: (p) => day(p.ama_date),
    sort: (p) => String(p.ama_date ?? "") },
  { id: "handover", label: "Key Handover", tight: true, cell: (p) => day(p.key_handover_date),
    sort: (p) => String(p.key_handover_date ?? "") },
  { id: "status", label: "Status", tight: true,
    cell: (p) => (<><span className={`stage ${AVAIL_CLASS[p.availability_status] ?? ""}`}>{p.availability_status}</span>
                   <div className="sub">{text(p.possession_status ?? p.occupancy_status)}</div></>),
    sort: (p) => p.availability_status },
  { id: "remarks", label: "Demand Team Remarks", cell: (p) => text(p.internal_remarks),
    sort: (p) => (p.internal_remarks ?? "").toLowerCase() },
  /* Off by default — every other field from the same row. They are ordinary table
     columns, not popup fields, so the settings modal lists them under "Hidden table
     columns"; `popup` is a lead-table distinction that means nothing here. */
  { id: "uid", label: "UID", tight: true, cell: (p) => p.uid, sort: (p) => p.uid },
  { id: "micro_market", label: "Micro-market", cell: (p) => text(p.micro_market),
    sort: (p) => (p.micro_market ?? "").toLowerCase() },
  { id: "tower", label: "Tower", tight: true, cell: (p) => text(p.tower_no),
    sort: (p) => String(p.tower_no ?? "") },
  { id: "unit", label: "Unit", tight: true, cell: (p) => text(p.unit_no),
    sort: (p) => String(p.unit_no ?? "") },
  { id: "floor", label: "Floor", tight: true, cell: (p) => text(p.floor),
    sort: (p) => String(p.floor ?? "") },
  { id: "supply_status", label: "Supply status", tight: true,
    cell: (p) => text(p.supply_status), sort: (p) => String(p.supply_status ?? "") },
  { id: "demand_status", label: "Demand status", tight: true,
    cell: (p) => text(p.demand_status), sort: (p) => String(p.demand_status ?? "") },
  { id: "possession", label: "Possession", tight: true,
    cell: (p) => text(p.possession_status ?? p.occupancy_status),
    sort: (p) => String(p.possession_status ?? p.occupancy_status ?? "") },
  { id: "source", label: "Source", tight: true, cell: (p) => text(p.source),
    sort: (p) => String(p.source ?? "") },
  { id: "poc", label: "POC", tight: true, cell: (p) => text(p.poc),
    sort: (p) => String(p.poc ?? "") },
  { id: "carpet", label: "Carpet area", tight: true, cell: (p) => num(p.carpet_area),
    sort: (p) => Number(p.carpet_area ?? 0) },
  { id: "furnishing", label: "Furnishing", tight: true, cell: (p) => text(p.furnishing),
    sort: (p) => String(p.furnishing ?? "") },
  { id: "parking", label: "Parking", tight: true, cell: (p) => text(p.parking),
    sort: (p) => String(p.parking ?? "") },
  { id: "affordable", label: "Affordable", tight: true,
    cell: (p) => (p.affordable === null || p.affordable === undefined ? "—" : p.affordable ? "Yes" : "No"),
    sort: (p) => String(p.affordable) },
  { id: "origin", label: "Record", tight: true,
    cell: (p) => (p.origin === "legacy" ? <span className="chip-soft">Legacy</span> : "—"),
    sort: (p) => p.origin },
];

/* Each box takes the hue of that status's CHIP in the Status column — `.stage.won` is
   emerald, `.stage.contacted` cyan, `.stage.new` blue (AVAIL_CLASS above). The box and
   the chip are the same fact in two places and must not be two colours. */
const AVAIL_BOXES = [
  { key: "Available", label: "Available", hue: "var(--emerald)" },
  { key: "Booked", label: "Booked", hue: "var(--cyan)" },
  { key: "Sold", label: "Sold", hue: "var(--blue)" },
];

const DD_BY_ID: Record<string, DDColumn> = Object.fromEntries(DEMAND_COLUMNS.map((c) => [c.id, c]));
/* their ten, in their order */
const DEMAND_COLS = ["society", "city", "locality", "config", "area", "price", "ama", "handover", "status", "remarks"];
/* module-level: an accessor object rebuilt each render re-sorts on every keystroke */
const SORTERS = Object.fromEntries(
  DEMAND_COLUMNS.filter((c) => c.sort).map((c) => [c.id, c.sort!]),
);

function PropertyModal({ p, onClose: raw }: { p: DemandProperty; onClose: () => void }) {
  const { onClose, overlayClass } = useModalExit(raw);
  const photos = photosOf(p);
  // Video is a link, not an image — it can't be a thumbnail, so it keeps its own row.
  const video = typeof p.video_link === "string" && p.video_link.trim() ? p.video_link : null;
  const [shot, setShot] = useState<Shot | null>(null);
  return createPortal(
    <div className={overlayClass} onClick={onClose}>
      <div className="modal dd-modal" onClick={(e) => e.stopPropagation()} role="dialog"
           aria-label={`${text(p.society_name)} ${text(p.unit_no)}`}>
        <div className="dd-head">
          <div>
            <h3>{text(p.society_name)}</h3>
            <div className="dd-sub">{unitLine(p)} · {text(p.city)}</div>
          </div>
          <span className={`stage ${AVAIL_CLASS[p.availability_status] ?? ""}`}>{p.availability_status}</span>
          {p.origin === "legacy" && <span className="chip-soft">Legacy</span>}
          <button className="modal-x" onClick={onClose} aria-label="Close"><IconX /></button>
        </div>
        <div className="dd-body">
          {SECTIONS.map((s) => (
            <div className="dd-section" key={s.title}>
              <div className="dd-section-t">{s.title}</div>
              <div className="dd-fields">
                {s.fields.map(([label, key, fmt]) => (
                  <div className={"field-row" + (WIDE.has(key) ? " dd-wide" : "")} key={key}>
                    <span className="field-lbl">{label}</span>
                    <span className="field-val">{(fmt ?? text)(p[key])}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {(photos.length > 0 || video) && (
            <div className="dd-section">
              <div className="dd-section-t">Media</div>
              <div className="dd-shots">
                {photos.map((ph, i) => (
                  <button className="dd-shot" key={ph.url}
                          onClick={(e) => { e.stopPropagation(); setShot({ ...ph, i }); }}
                          title={`${ph.label} — click to enlarge`}>
                    {/* lazy: a property carries up to ~10 photos and most are never looked at */}
                    <img src={ph.url} alt={ph.label} loading="lazy" />
                    <span className="dd-shot-l">{ph.label}</span>
                  </button>
                ))}
              </div>
              {/* The walkthrough is the one thing here worth opening before a call — it
                  gets the accent, not a line of link text among the thumbnails. */}
              {video && (
                <a className="btn primary dd-video" href={video} target="_blank" rel="noreferrer">
                  <IconPlay /> Video walkthrough
                </a>
              )}
            </div>
          )}
        </div>
      </div>
      {shot && <Lightbox shot={shot} all={photos} onPick={setShot} onClose={() => setShot(null)} />}
    </div>,
    document.body,
  );
}

type Shot = { url: string; label: string; i: number };

/* Every photo on a property, in the order somebody would look at them: the balconies
   first (each with its view and compass shot), then the unit's own exit compass, then
   anything in additional_images. Labelled, because eight Cloudinary URLs are otherwise
   indistinguishable. */
function photosOf(p: DemandProperty): { url: string; label: string }[] {
  const out: { url: string; label: string }[] = [];
  const push = (url: unknown, label: string) => {
    if (typeof url === "string" && url.startsWith("http")) out.push({ url, label });
  };
  (Array.isArray(p.balcony_details) ? p.balcony_details : []).forEach((b, i) => {
    const o = (b ?? {}) as Record<string, unknown>;
    const name = `Balcony ${o.index ?? i + 1}`;
    push(o.view_image, `${name} view`);
    push(o.compass_image, `${name} compass`);
  });
  push(p.exit_compass_image, "Exit compass");
  (Array.isArray(p.additional_images) ? p.additional_images : []).forEach((u, i) => push(u, `Photo ${i + 1}`));
  return out;
}

/* The photo full size, over the popup. It is its own modal so Escape closes the PHOTO
   first and leaves the property open — `useModalExit` only lets the topmost one react.
   ← / → walk the set, because comparing two balconies is the reason to open one. */
function Lightbox({ shot, all, onPick, onClose: raw }: {
  shot: Shot; all: { url: string; label: string }[];
  onPick: (s: Shot) => void; onClose: () => void;
}) {
  const { onClose, overlayClass } = useModalExit(raw);
  const step = (d: number) => {
    const i = (shot.i + d + all.length) % all.length;
    onPick({ ...all[i], i });
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") step(1);
      if (e.key === "ArrowLeft") step(-1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
  /* ⚠️ stopPropagation is load-bearing: the lightbox is rendered INSIDE the property
     popup's own overlay, whose onClick closes the property. A React event bubbles up the
     COMPONENT tree even through a portal, so dismissing the photo was also dismissing the
     property behind it. Same reason the buttons below stop their clicks. */
  const dismiss = (e: React.MouseEvent) => { e.stopPropagation(); onClose(); };
  return (
    <div className={`${overlayClass} dd-lightbox`} onClick={dismiss}>
      <figure className="dd-lb-inner" onClick={(e) => e.stopPropagation()}>
        <img src={shot.url} alt={shot.label} />
        <figcaption>
          {all.length > 1 && (
            <button className="btn ghost sm" onClick={(e) => { e.stopPropagation(); step(-1); }}
                    aria-label="Previous photo">‹</button>
          )}
          <span>{shot.label}{all.length > 1 && ` · ${shot.i + 1} of ${all.length}`}</span>
          {all.length > 1 && (
            <button className="btn ghost sm" onClick={(e) => { e.stopPropagation(); step(1); }}
                    aria-label="Next photo">›</button>
          )}
          <a className="dd-link" href={shot.url} target="_blank" rel="noreferrer">Open original</a>
        </figcaption>
        <button className="modal-x" onClick={dismiss} aria-label="Close"><IconX /></button>
      </figure>
    </div>
  );
}

export default function DemandDashboard() {
  const { data, isLoading } = useDemandProperties();
  const all = data?.items ?? [];
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [open, setOpen] = useState<DemandProperty | null>(null);
  // City is the tab row, not a dropdown — same control, and the same `cityMatches`
  // rule, as every lead list. Invalid City is what makes a row with no city (or one
  // outside the three) reachable at all.
  const [cityTab, setCityTab] = useState("");
  // Several areas at once is the real question here ("Gr Noida West + Noida Extension"),
  // which a single-value <select> cannot ask.
  const [markets, setMarkets] = useState<string[]>([]);
  // The status boxes own availability, like the stage boxes own stage: its own state,
  // not a FilterBar value, so a pick isn't also a removable chip.
  const [avail, setAvail] = useState("");
  const { values: f, set, clear } = useFilterValues({
    possession: "", source: "", poc: "", affordable: "",
  });

  /* `pass(p, skip)` applies every filter except `skip`, so each dropdown counts the rows
     passing all the OTHERS — the same faceting every list page here uses. */
  const pass = (p: DemandProperty, skip?: string) =>
    (skip === "city" || cityMatches(p.city, cityTab)) &&
    (skip === "micro_market" || !markets.length || markets.includes(p.micro_market ?? "")) &&
    (skip === "availability" || !avail || p.availability_status === avail) &&
    (skip === "possession" || matchesOption(p.possession_status ?? p.occupancy_status, f.possession)) &&
    (skip === "source" || matchesOption(p.source, f.source)) &&
    (skip === "poc" || matchesOption(p.poc, f.poc)) &&
    (!f.affordable || String(p.affordable === true) === (f.affordable === "yes" ? "true" : "false")) &&
    matchesQuery(p, applied);

  /* Faceted like every other filter: each area's count is over the rows passing all the
     OTHER filters, so the numbers don't collapse once one is ticked. */
  const marketOptions = (() => {
    const n = new Map<string, number>();
    for (const p of all.filter((x) => pass(x, "micro_market"))) {
      const m = (p.micro_market ?? "").trim();
      if (m) n.set(m, (n.get(m) ?? 0) + 1);
    }
    return [...n.entries()].sort((a, b) => a[0].localeCompare(b[0]))
      .map(([value, count]) => ({ value, label: value, count }));
  })();

  const rows = all.filter((p) => pass(p));
  const { sorted, sortKey, dir, onSort } = useSort<DemandProperty>(rows, SORTERS);
  // same Columns control as the lead tables, driven by this page's own registry
  const columns = useLeadColumns("demand-dashboard", DEMAND_COLS, "Demand Dashboard", DEMAND_COLUMNS);
  const pg = usePaging(sorted);

  return (
    <>
      <TopbarSlot>{columns.button}</TopbarSlot>
      {columns.modal}
      <div className="lead-toolbar">
        <SlideTabs className="city-tabs" activeSelector=".tab-active">
          <button className={!cityTab ? "tab tab-active" : "tab"} onClick={() => setCityTab("")}>All</button>
          {CITY_TABS.map((c) => (
            <button key={c} className={cityTab === c ? "tab tab-active" : "tab"}
                    onClick={() => setCityTab(c)}>{c}</button>
          ))}
        </SlideTabs>
        <MultiSelect label="Micro-market" value={markets} onChange={setMarkets}
          options={marketOptions} />
        {/* The same `.search-form` every lead list uses — apply-on-submit, with Clear
            appearing once applied. Hand-rolling it here gave a square, unsized box. */}
        <form className="search-form" onSubmit={(e) => { e.preventDefault(); setApplied(q); }}>
          <input value={q} placeholder="Search any field — e.g. 1709 Sahaj"
                 onChange={(e) => setQ(e.target.value)} />
          <button type="submit" className="btn primary"><IconSearch /> Search</button>
          {applied && (
            <button type="button" className="btn ghost"
                    onClick={() => { setQ(""); setApplied(""); }}><IconX /> Clear</button>
          )}
        </form>
        <FilterBar
          fields={[
            { key: "possession", label: "Possession", options: countedOptions(all.filter((p) => pass(p, "possession")), (p) => p.possession_status ?? p.occupancy_status) },
            { key: "source", label: "Source", options: countedOptions(all.filter((p) => pass(p, "source")), (p) => p.source) },
            { key: "poc", label: "POC", options: countedOptions(all.filter((p) => pass(p, "poc")), (p) => p.poc) },
            { key: "affordable", label: "Affordable", options: [{ value: "yes", label: "Yes" }, { value: "no", label: "No" }] },
          ]}
          values={f} onChange={set} onClear={clear}
        />
      </div>

      {/* Availability as count boxes, the same `.count-pill` row the lead pages use.
          Counted with every filter EXCEPT this one, so picking one doesn't zero the rest,
          and the three always sum to ALL. */}
      <StageBoxes total={all.filter((p) => pass(p, "availability")).length} loading={isLoading}
        extra={AVAIL_BOXES.map((b) => ({ ...b,
          count: all.filter((p) => pass(p, "availability") && p.availability_status === b.key).length }))}
        extraValue={avail} onExtra={setAvail} />

      <Pager page={pg.page} pages={pg.pages} size={pg.size} total={sorted.length} onPage={pg.setPage}
             sizeChoice={pg.sizeChoice} onSize={pg.setSize} />

      <div className="card table-wrap">
        <table className="tbl">
          <thead>
            <tr>
              {columns.cols.map((id) => DD_BY_ID[id]).filter(Boolean).map((c) => (
                c.sort
                  ? <SortTh key={c.id} sortKey={c.id} label={c.label} activeKey={sortKey}
                            dir={dir} onSort={onSort} />
                  : <th key={c.id} className={c.tight ? "cell-tight" : undefined}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <SkeletonTable rows={8} cols={columns.cols.length} />
            ) : !pg.slice.length ? (
              <tr><td colSpan={columns.cols.length}><div className="empty" style={{ padding: 24 }}>No properties match these filters.</div></td></tr>
            ) : pg.slice.map((p) => (
              <tr key={p.uid} className="row-open" onClick={() => setOpen(p)}>
                {columns.cols.map((id) => DD_BY_ID[id]).filter(Boolean).map((c) => (
                  <td key={c.id} className={c.tight ? "cell-tight" : "cell-text"}>{c.cell(p)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && <PropertyModal p={open} onClose={() => setOpen(null)} />}
    </>
  );
}

/* Search runs over the fields a person would type: the ones on the row plus the UID. */
function matchesQuery(p: DemandProperty, q: string): boolean {
  const s = q.trim().toLowerCase();
  if (!s) return true;
  return [p.uid, p.society_name, p.unit_no, p.tower_no, p.city, p.locality, p.micro_market,
          p.configuration, p.poc, p.source]
    .some((v) => String(v ?? "").toLowerCase().includes(s));
}
