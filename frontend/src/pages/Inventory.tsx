/* Live Inventory — the Demand CRM's Inventory Snapshot, rebuilt here.

   A share-first view rather than a browse-first one: city → micro-market → unit table,
   multi-select filters that narrow what the exports contain, and two exports off the
   same filtered set — a WhatsApp-ready text block and a rasterized PNG poster.

   Field derivation lives in lib/snapshot.ts; this file is rendering and state. */
import {
  forwardRef,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useInventory, useSyncInventory } from "../lib/queries";
import { InventoryItem } from "../lib/api";
import { useToast } from "../components/Toast";
import { useAuth } from "../components/AuthContext";
import { useSearch, matches } from "../components/SearchContext";
import { useStickyState } from "../lib/sessionFilters";
import useIsMobile from "../lib/useIsMobile";
import { waShare } from "../lib/whatsapp";
import {
  citySub,
  citiesOf,
  buildShareText,
  configOf,
  cityOf,
  fmtDate,
  groupPropertiesByCity,
  isNew,
  isSellable,
  localityOf,
  microMarketOf,
  pmOf,
  priceLabel,
  priceLacsOf,
  priceTextOf,
  societyOf,
  sqftOf,
  statusKind,
  statusOf,
  statusRank,
  TODAY,
  unitOf,
  ymd,
  type CityGroup,
} from "../lib/snapshot";

/* ============================== multi-select ============================== */
/* Dependency-free checkbox dropdown — the CRM's, same classes. */
function MultiSelect({
  label,
  options,
  value,
  onChange,
  width,
}: {
  label: string;
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
  width?: number;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  const shown = q ? options.filter((o) => o.toLowerCase().includes(q.toLowerCase())) : options;
  const toggle = (val: string) =>
    onChange(value.includes(val) ? value.filter((x) => x !== val) : [...value, val]);

  return (
    <div className="an-ms" ref={ref} style={width ? { width } : undefined}>
      <button
        type="button"
        className={"an-ms-btn" + (value.length ? " has" : "")}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
        {value.length ? <span className="an-ms-count">{value.length}</span> : null}
        <span className="an-ms-caret">▾</span>
      </button>
      {open && (
        <div className="an-ms-pop">
          <input
            className="an-ms-search"
            autoFocus
            placeholder={`Search ${label.toLowerCase()}…`}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="an-ms-actions">
            <button type="button" onClick={() => onChange(shown)}>All</button>
            <button type="button" onClick={() => onChange([])}>Clear</button>
            <span className="an-ms-n">{value.length} selected</span>
          </div>
          <div className="an-ms-list">
            {shown.slice(0, 400).map((o) => (
              <label key={o} className="an-ms-opt">
                <input type="checkbox" checked={value.includes(o)} onChange={() => toggle(o)} />
                <span>{o}</span>
              </label>
            ))}
            {shown.length > 400 && (
              <div className="an-ms-more">+{shown.length - 400} more — refine search</div>
            )}
            {shown.length === 0 && <div className="an-ms-more">No matches</div>}
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================== page ============================== */

interface ShareState {
  title: string;
  text: string;
}
interface ImgState {
  props: InventoryItem[];
  title: string;
  subtitle: string;
  filebase: string;
  dataUrl: string | null;
  loading: boolean;
  canvas: HTMLCanvasElement | null;
}

const sameSet = (a: string[], b: string[]) =>
  a.length === b.length && a.every((x) => b.includes(x));

export default function Inventory() {
  const { data, isLoading } = useInventory();
  const sync = useSyncInventory();
  const toast = useToast();
  const { user } = useAuth();
  const { query, setQuery } = useSearch();

  const all = useMemo(() => data?.items ?? [], [data]);

  /* ----------------------------- filter state ----------------------------- */
  const [fCities, setFCities] = useStickyState<string[]>("snapshot:fCities", []);
  const [fConfigs, setFConfigs] = useStickyState<string[]>("snapshot:fConfigs", []);
  const [fRegions, setFRegions] = useStickyState<string[]>("snapshot:fRegions", []);
  const [priceMin, setPriceMin] = useStickyState<string>("snapshot:priceMin", "");
  const [priceMax, setPriceMax] = useStickyState<string>("snapshot:priceMax", "");
  /* null = "still on the default". The default is the sellable subset of whatever
     statuses the data actually holds, which isn't knowable until the fetch lands —
     so it can't be a literal initial value the way the CRM's was. */
  const [fStatusesRaw, setFStatuses] = useStickyState<string[] | null>("snapshot:fStatuses", null);

  /* distinct option lists, off the full set */
  const cityOpts = useMemo(() => citiesOf(all), [all]);
  const configOpts = useMemo(() => {
    const s = new Set<string>();
    all.forEach((p) => { const c = configOf(p); if (c) s.add(c); });
    return [...s].sort((a, b) => a.localeCompare(b));
  }, [all]);
  const regionOpts = useMemo(() => {
    const s = new Set<string>();
    all.forEach((p) => { const m = microMarketOf(p); if (m) s.add(m); });
    return [...s].sort((a, b) => a.localeCompare(b));
  }, [all]);
  const statusOpts = useMemo(() => {
    const s = new Set<string>();
    all.forEach((p) => { const st = statusOf(p); if (st) s.add(st); });
    return [...s].sort((a, b) => statusRank(a) - statusRank(b) || a.localeCompare(b));
  }, [all]);

  const defaultStatuses = useMemo(() => statusOpts.filter(isSellable), [statusOpts]);
  const fStatuses = fStatusesRaw ?? defaultStatuses;

  /* inputs are in CRORES (the natural unit for these listings) → lacs, which is what
     the backend already parsed price_lacs into. 0.75 = 75 L works too. */
  const minLacs = useMemo(() => {
    const n = parseFloat(priceMin);
    return Number.isFinite(n) && n > 0 ? n * 100 : null;
  }, [priceMin]);
  const maxLacs = useMemo(() => {
    const n = parseFloat(priceMax);
    return Number.isFinite(n) && n > 0 ? n * 100 : null;
  }, [priceMax]);

  const statusChanged = fStatusesRaw !== null && !sameSet(fStatusesRaw, defaultStatuses);
  const hasFilters = !!(
    fCities.length ||
    fConfigs.length ||
    fRegions.length ||
    minLacs != null ||
    maxLacs != null ||
    statusChanged ||
    query.trim()
  );

  /* one pass, before grouping / counts / poster, so everything downstream agrees */
  const filtered = useMemo(
    () =>
      all.filter((p) => {
        if (fStatuses.length && !fStatuses.includes(statusOf(p))) return false;
        if (fCities.length && !fCities.includes(cityOf(p))) return false;
        if (fConfigs.length && !fConfigs.includes(configOf(p))) return false;
        if (fRegions.length && !fRegions.includes(microMarketOf(p))) return false;
        if (minLacs != null || maxLacs != null) {
          const v = priceLacsOf(p);
          if (v == null) return false;
          if (minLacs != null && v < minLacs) return false;
          if (maxLacs != null && v > maxLacs) return false;
        }
        return matches(
          query,
          societyOf(p),
          unitOf(p),
          localityOf(p),
          microMarketOf(p),
          configOf(p),
          cityOf(p),
          statusOf(p),
        );
      }),
    [all, fStatuses, fCities, fConfigs, fRegions, minLacs, maxLacs, query],
  );

  const clearFilters = useCallback(() => {
    setFCities([]);
    setFConfigs([]);
    setFRegions([]);
    setPriceMin("");
    setPriceMax("");
    setFStatuses(null);
    // the topbar search narrows this list too, so "reset" has to include it — otherwise
    // the button clears every control the user can see and the list stays filtered
    setQuery("");
  }, [setFCities, setFConfigs, setFRegions, setPriceMin, setPriceMax, setFStatuses, setQuery]);

  const grouped = useMemo(() => groupPropertiesByCity(filtered), [filtered]);
  const cities = useMemo(
    () => citiesOf(filtered).filter((c) => grouped[c]?.total),
    [filtered, grouped],
  );
  const totalReady = useMemo(
    () => filtered.filter((p) => statusKind(statusOf(p)) === "r").length,
    [filtered],
  );
  const totalCS = useMemo(
    () => filtered.filter((p) => statusKind(statusOf(p)) === "cs").length,
    [filtered],
  );

  const [share, setShare] = useState<ShareState | null>(null);
  const [img, setImg] = useState<ImgState | null>(null);
  const posterRef = useRef<HTMLDivElement>(null);

  const countLabel = hasFilters
    ? `${filtered.length} units match · ${totalReady} available · ${totalCS} coming soon`
    : `${all.length} live properties · ${totalReady} available · ${totalCS} coming soon · share-ready snapshot`;

  /* title fragments from the active filters, used by the filtered share */
  const filterTitleBits = useMemo(() => {
    const bits: string[] = [];
    if (fConfigs.length) bits.push(fConfigs.join(" / "));
    if (fCities.length) bits.push(fCities.join(" & "));
    if (fRegions.length) bits.push(fRegions.join(" / "));
    const pl = priceLabel(
      minLacs != null ? minLacs / 100 : null,
      maxLacs != null ? maxLacs / 100 : null,
    );
    if (pl) bits.push(pl);
    return bits;
  }, [fConfigs, fCities, fRegions, minLacs, maxLacs]);

  /* ----------------------------- text share ----------------------------- */
  const openShare = useCallback(
    (target: string[]) => {
      const props = filtered.filter((p) => target.includes(cityOf(p)));
      setShare({
        title: `Inventory snapshot · ${target.join(" & ")}`,
        text: buildShareText(props, `Openhouse Live Inventory · ${target.join(" & ")}`, user?.name),
      });
    },
    [filtered, user?.name],
  );

  /* ----------------------------- image export ----------------------------- */
  const openImage = useCallback(
    (props: InventoryItem[], title: string, subtitle: string, filebase: string) => {
      setImg({ props, title, subtitle, filebase, dataUrl: null, loading: true, canvas: null });
    },
    [],
  );
  const openCityImage = useCallback(
    (target: string[]) => {
      openImage(
        filtered.filter((p) => target.includes(cityOf(p))),
        `Snapshot · ${target.join(" & ")}`,
        target.join(" · "),
        target.join("-").toLowerCase(),
      );
    },
    [filtered, openImage],
  );
  const openFilteredImage = useCallback(() => {
    const bits = filterTitleBits.length ? filterTitleBits.join(" · ") : "Full Inventory";
    openImage(filtered, `Openhouse · ${bits}`, bits, "filtered");
  }, [filtered, filterTitleBits, openImage]);

  /* render the off-screen poster, then rasterize it */
  useEffect(() => {
    if (!img || !img.loading) return;
    let cancelled = false;
    (async () => {
      try {
        // code-split: html2canvas only ships to the browser when someone exports
        const { default: html2canvas } = await import("html2canvas");
        // give the off-screen poster a frame to lay out
        await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
        if (cancelled || !posterRef.current) return;
        const canvas = await html2canvas(posterRef.current, {
          scale: 2,
          backgroundColor: "#FFFFFF",
          logging: false,
          useCORS: true,
        });
        if (cancelled) return;
        setImg((cur) =>
          cur ? { ...cur, loading: false, dataUrl: canvas.toDataURL("image/png"), canvas } : cur,
        );
      } catch {
        if (cancelled) return;
        toast("Image generation failed", "gold", "⚠");
        setImg((cur) => (cur ? { ...cur, loading: false, dataUrl: null, canvas: null } : cur));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [img, toast]);

  const notReady = data && data.status !== "ok";

  return (
    <div className="snap-page">
      {/* ----------------------------- filter bar ----------------------------- */}
      <div className="snap-filters">
        <div className="snap-filters-row">
          <span className="snap-filters-lbl">Build a request-specific share</span>
          <MultiSelect label="City" options={cityOpts} value={fCities} onChange={setFCities} />
          <MultiSelect label="BHK / Config" options={configOpts} value={fConfigs} onChange={setFConfigs} />
          <MultiSelect label="Region" options={regionOpts} value={fRegions} onChange={setFRegions} />
          <MultiSelect label="Status" options={statusOpts} value={fStatuses} onChange={setFStatuses} />
          <div className="snap-price">
            <span className="snap-price-lbl">Price (₹ Cr)</span>
            <input
              type="number" inputMode="decimal" min="0" step="0.25" placeholder="1.5"
              className="snap-price-in" value={priceMin}
              onChange={(e) => setPriceMin(e.target.value)}
            />
            <span className="snap-price-dash">–</span>
            <input
              type="number" inputMode="decimal" min="0" step="0.25" placeholder="2"
              className="snap-price-in" value={priceMax}
              onChange={(e) => setPriceMax(e.target.value)}
            />
          </div>
          {hasFilters ? (
            <button type="button" className="an-chip clear" onClick={clearFilters}>↺ Reset filters</button>
          ) : null}
        </div>
        <div className="snap-filters-row">
          <span className={"snap-match" + (filtered.length ? "" : " zero")}>
            <strong>{filtered.length}</strong> {filtered.length === 1 ? "unit" : "units"} match
            {filterTitleBits.length ? (
              <span className="snap-match-sub"> · {filterTitleBits.join(" · ")}</span>
            ) : null}
          </span>
          <button
            type="button"
            className="btn primary"
            disabled={!filtered.length}
            onClick={openFilteredImage}
          >
            🖼 Share filtered selection
          </button>
        </div>
      </div>

      <div className="list-head" style={{ flexWrap: "wrap", gap: 10 }}>
        <span>{countLabel}</span>
        <div className="pager" style={{ flexWrap: "wrap", gap: 6 }}>
          <span className="snap-share-lbl">As image:</span>
          <button className="btn sm primary" onClick={() => openCityImage(["Gurgaon"])}>🖼 Gurgaon</button>
          <button className="btn sm primary" onClick={() => openCityImage(["Noida"])}>🖼 Noida</button>
          <button className="btn sm primary" onClick={() => openCityImage(["Ghaziabad"])}>🖼 Ghaziabad</button>
          <button className="btn sm primary" onClick={() => openCityImage(["Noida", "Ghaziabad"])}>🖼 Noida + Ghaziabad</button>
          <span className="snap-share-lbl">As text:</span>
          <button className="btn sm" onClick={() => openShare(["Gurgaon"])}>📤 Gurgaon</button>
          <button className="btn sm" onClick={() => openShare(["Noida"])}>📤 Noida</button>
          <button className="btn sm" onClick={() => openShare(["Ghaziabad"])}>📤 Ghaziabad</button>
          <button className="btn sm" onClick={() => openShare(["Noida", "Ghaziabad"])}>📤 NCR</button>
          <button
            className="btn sm"
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

      <div>
        {isLoading ? (
          <div className="empty">
            <div className="emoji">⏳</div>
            <div className="t">Loading inventory…</div>
          </div>
        ) : notReady ? (
          <div className="empty">
            <div className="emoji">⚠️</div>
            <div className="t">Inventory not available</div>
            <div className="s">{data?.detail || "Sync is not configured yet."}</div>
          </div>
        ) : cities.length === 0 ? (
          <div className="empty">
            <div className="emoji">📦</div>
            <div className="t">
              {all.length === 0 ? "No inventory loaded" : "No units match these filters"}
            </div>
          </div>
        ) : (
          cities.map((city) => <CityBlock key={city} city={city} g={grouped[city]} />)
        )}
      </div>

      {share && <ShareModal share={share} onClose={() => setShare(null)} />}
      {img && (
        <ImageModal img={img} onClose={() => setImg(null)}>
          {/* off-screen poster — html2canvas rasterizes this DOM node */}
          {img.loading && <Poster ref={posterRef} props={img.props} title={img.subtitle} />}
        </ImageModal>
      )}
    </div>
  );
}

/* ============================== city block ============================== */
function CityBlock({ city, g }: { city: string; g: CityGroup }) {
  const isMobile = useIsMobile();
  const counts = useMemo(() => {
    let r = 0, cs = 0, bk = 0;
    g.ordered.forEach((mm) =>
      g.mmGroups[mm].forEach((p) => {
        const k = statusKind(statusOf(p));
        if (k === "r") r += 1;
        else if (k === "cs") cs += 1;
        else if (k === "bk") bk += 1;
      }),
    );
    return { r, cs, bk };
  }, [g]);

  return (
    <div className="snap-city">
      <div className="snap-city-head">
        <div>
          <h2>{city} · {g.total} units</h2>
          <div className="sub">{citySub(city)}</div>
        </div>
        <div className="count-pills">
          <span className="cp">{counts.r} Available</span>
          {counts.cs ? <span className="cp">{counts.cs} Coming Soon</span> : null}
          {counts.bk ? <span className="cp">{counts.bk} Booked</span> : null}
        </div>
      </div>

      {g.ordered.map((mm) => {
        const props = g.mmGroups[mm];
        return (
          <div className="snap-cluster" key={mm}>
            <div className="snap-cluster-head">{mm} · {props.length}</div>
            {isMobile ? (
              <div className="snap-mlist">
                {props.map((p, i) => (
                  <div className="snap-mcard" key={p.id ?? i}>
                    <div className="smc-top">
                      <span className="smc-soc">
                        {isNew(p) ? <span className="new-badge">NEW</span> : null}
                        {societyOf(p) || "—"}
                      </span>
                      <span className={`status-pill ${statusKind(statusOf(p))}`}>
                        {statusOf(p) || "—"}
                      </span>
                    </div>
                    <div className="smc-meta">
                      {unitOf(p)} · {configOf(p) || "—"} · {sqftOf(p) || "—"} sqft ·{" "}
                      {localityOf(p) || "—"}
                    </div>
                    <div className="smc-meta">PM · {pmOf(p) || "—"}</div>
                    <div className="smc-price">{priceTextOf(p)}</div>
                  </div>
                ))}
              </div>
            ) : (
              <table className="snap-tbl">
                <colgroup>
                  <col className="col-soc" /><col className="col-unit" /><col className="col-area" />
                  <col className="col-cfg" /><col className="col-loc" /><col className="col-status" /><col className="col-price" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Society</th><th>Unit</th><th>Area</th><th>Config</th>
                    <th>Locality</th><th>Status</th><th className="right">Ask Price</th>
                  </tr>
                </thead>
                <tbody>
                  {props.map((p, i) => (
                    <tr key={p.id ?? i}>
                      <td className="cell-society" title={societyOf(p)}>
                        <span className="society">
                          {isNew(p) ? <span className="new-badge">NEW</span> : null}
                          {societyOf(p) || "—"}
                        </span>
                        <div className="cell-pm">PM · {pmOf(p) || "—"}</div>
                      </td>
                      <td className="cell-unit"><span className="unit">{unitOf(p)}</span></td>
                      <td className="cell-area"><span className="area">{sqftOf(p) || "—"} sqft</span></td>
                      <td className="cell-cfg"><span className="cfg">{configOf(p) || "—"}</span></td>
                      <td className="cell-loc" title={localityOf(p)}>{localityOf(p) || "—"}</td>
                      <td className="cell-status">
                        <span className={`status-pill ${statusKind(statusOf(p))}`}>
                          {statusOf(p) || "—"}
                        </span>
                      </td>
                      <td className="cell-price right"><span className="ask-price">{priceTextOf(p)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ============================== text share modal ============================== */
function ShareModal({ share, onClose }: { share: ShareState; onClose: () => void }) {
  const toast = useToast();
  const [text, setText] = useState(share.text);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const copy = () => {
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text)
        .then(() => toast("Snapshot copied — paste in any chat", "green", "📋"))
        .catch(() => toast("Copy failed", "gold", "⚠"));
    } else {
      toast("Clipboard unavailable", "gold", "⚠");
    }
  };
  const sendWa = () => {
    waShare(text);
    onClose();
  };

  return (
    <div className="modal-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" style={{ width: 620, maxWidth: "96vw", maxHeight: "96vh" }}>
        <div className="modal-head">
          <h2>{share.title}</h2>
          <button className="x-btn" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <div className="snap-modal-hint">
            Inventory snapshot ready to share. Tap below to open WhatsApp with a recipient
            picker, or copy and paste anywhere.
          </div>
          <textarea
            className="snap-share-ta"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="snap-modal-actions">
            <button className="btn" onClick={copy}>📋 Copy to clipboard</button>
            <button className="btn primary" onClick={sendWa}>📤 Share via WhatsApp</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============================== image export modal ============================== */
function ImageModal({
  img,
  onClose,
  children,
}: {
  img: ImgState;
  onClose: () => void;
  children?: ReactNode;
}) {
  const toast = useToast();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const filename = `openhouse-${img.filebase || "inventory"}-${ymd(TODAY)}.png`;

  const download = () => {
    if (!img.dataUrl) return;
    const a = document.createElement("a");
    a.href = img.dataUrl;
    a.download = filename;
    a.click();
    toast("Image downloaded", "green", "⬇️");
  };
  const copy = () => {
    if (!img.canvas) return;
    try {
      img.canvas.toBlob(async (blob) => {
        if (blob && navigator.clipboard?.write) {
          await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
          toast("Image copied to clipboard", "green", "📋");
        } else {
          toast("Clipboard not supported — use Download", "gold", "⚠");
        }
      }, "image/png");
    } catch {
      toast("Copy failed — use Download", "gold", "⚠");
    }
  };
  /* wa.me can't carry an attachment, so the image is downloaded first and the chat
     opens with the caption — the user attaches the file they just got. */
  const whatsapp = () => {
    if (!img.dataUrl) return;
    const a = document.createElement("a");
    a.href = img.dataUrl;
    a.download = filename;
    a.click();
    setTimeout(() => {
      waShare(
        `${img.title} · ${fmtDate(TODAY)}\n\nAttached image has the latest unit list. Ping me for any visit / pricing detail.`,
      );
      toast("Image downloaded — attach it in WhatsApp", "green", "📤");
    }, 400);
  };

  return (
    <div className="modal-bg snap-img-modal" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" style={{ width: 880, maxWidth: "96vw", maxHeight: "96vh" }}>
        <div className="modal-head">
          <h2>{img.title}</h2>
          <button className="x-btn" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          {img.loading ? (
            <div className="snap-loading">
              <div className="spinner" />
              Generating beautiful image…
            </div>
          ) : img.dataUrl ? (
            <div className="snap-preview"><img src={img.dataUrl} alt="Inventory snapshot" /></div>
          ) : (
            <div className="empty"><div className="emoji">⚠️</div><div className="t">Could not render image</div></div>
          )}
          {/* off-screen poster lives here during loading */}
          {children}
        </div>
        <div className="modal-foot">
          <span className="snap-modal-hint">PNG · ready to share in WhatsApp/Email</span>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn" disabled={!img.canvas} onClick={copy}>📋 Copy image</button>
            <button className="btn" disabled={!img.dataUrl} onClick={download}>⬇️ Download PNG</button>
            <button className="btn primary" disabled={!img.dataUrl} onClick={whatsapp}>📤 Open WhatsApp</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============================== poster (off-screen, for html2canvas) ============================== */
/* Inline Openhouse mark — there's no symbol registry here, so the poster carries the
   literal paths and rasterizes crisply. */
const OH_ICON = (
  <svg viewBox="0 0 190 188">
    <path d="M79.5801 124.831C79.5801 122.469 81.9388 120.807 84.2094 121.569L108.648 129.771C110.065 130.247 111.018 131.559 111.018 133.033V174.825C111.018 176.229 110.152 177.493 108.83 178.019L84.3918 187.746C82.091 188.661 79.5801 186.994 79.5801 184.551V124.831Z" fill="#FA541C" />
    <path fillRule="evenodd" clipRule="evenodd" d="M189.614 94.4359C189.614 131.293 168.528 163.219 137.774 178.777C132.092 181.651 126.08 183.967 119.809 185.652V117.435C119.809 103.952 108.894 93.0228 95.4285 93.0228C81.9635 93.0228 71.0476 103.952 71.0476 117.435V185.721C64.7793 184.055 58.7673 181.76 53.083 178.906C22.1898 163.396 0.984863 131.396 0.984863 94.4359C0.984863 42.2806 43.2114 0 95.3001 0C147.389 0 189.614 42.2806 189.614 94.4359ZM171.649 94.4359C171.649 120.904 158.207 144.253 137.774 157.978V117.435C137.774 94.018 118.815 75.0349 95.4285 75.0349C86.3282 75.0349 77.8985 77.9092 70.9953 82.8005V21.9429C78.6298 19.3778 86.8028 17.9879 95.3001 17.9879C137.467 17.9879 171.649 52.2146 171.649 94.4359ZM53.1582 30.6778C32.5424 44.3665 18.9499 67.8117 18.9499 94.4359C18.9499 121.014 32.5046 144.448 53.083 158.149V117.435C53.083 116.579 53.1083 115.729 53.1582 114.886V30.6778Z" fill="#161C24" />
  </svg>
);

const Poster = forwardRef<HTMLDivElement, { props: InventoryItem[]; title: string }>(
  function Poster({ props, title }, ref) {
    const ready = props.filter((p) => statusKind(statusOf(p)) === "r").length;
    const cities = citiesOf(props);

    return (
      <div className="poster" ref={ref}>
        <div className="ph">
          {OH_ICON}
          <div>
            <div className="pht">Openhouse · Live Inventory</div>
            <div className="phs">{title || cities.join(" · ")}</div>
          </div>
          <div className="phd">
            {fmtDate(TODAY)}
            <br />{props.length} units · {ready} available
          </div>
        </div>

        {cities.map((city) => {
          const cityProps = props.filter((p) => cityOf(p) === city);
          if (!cityProps.length) return null;
          const cReady = cityProps.filter((p) => statusKind(statusOf(p)) === "r").length;
          const cCS = cityProps.filter((p) => statusKind(statusOf(p)) === "cs").length;
          const mmGroups: Record<string, InventoryItem[]> = {};
          cityProps.forEach((p) => {
            const k = microMarketOf(p) || "Other";
            (mmGroups[k] = mmGroups[k] || []).push(p);
          });
          const mmOrder = Object.keys(mmGroups).sort();
          return (
            <div className="pcity" key={city || "other"}>
              <div className="pcity-hd">
                <h3>{city || "Other"} · {cityProps.length} units</h3>
                <div>
                  <span className="cnt">{cReady} Available</span>
                  {cCS ? <> <span className="cnt">{cCS} Coming Soon</span></> : null}
                </div>
              </div>
              {mmOrder.map((mm) => {
                const list = mmGroups[mm]
                  .slice()
                  .sort((a, b) => societyOf(a).localeCompare(societyOf(b)));
                return (
                  <div className="pcluster" key={mm}>
                    <div className="phl">{mm} · {list.length}</div>
                    <table>
                      <thead>
                        <tr>
                          <th>Society</th><th>Unit</th><th>Cfg</th><th>Sqft</th><th>Status</th>
                          <th style={{ textAlign: "right" }}>Price</th>
                        </tr>
                      </thead>
                      <tbody>
                        {list.map((p, i) => (
                          <tr key={p.id ?? i}>
                            <td>
                              <span className="ps-soc">
                                {isNew(p) ? <span className="pnew">NEW</span> : null}
                                {societyOf(p) || "—"}
                              </span>
                              {localityOf(p) ? <div className="ps-loc">{localityOf(p)}</div> : null}
                            </td>
                            <td><span className="ps-unit">{unitOf(p)}</span></td>
                            <td>{configOf(p) || "—"}</td>
                            <td>{sqftOf(p) || "—"}</td>
                            <td>
                              <span className={`ps-status ${statusKind(statusOf(p))}`}>
                                {statusOf(p) || "—"}
                              </span>
                            </td>
                            <td style={{ textAlign: "right" }}>
                              <span className="ps-price">{priceTextOf(p)}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })}
            </div>
          );
        })}

        <div className="pfoot">
          Reach out to your Openhouse RM for site visits, virtual tour or pricing · Updated {fmtDate(TODAY)}
        </div>
      </div>
    );
  },
);
