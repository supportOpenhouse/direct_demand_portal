/* Visit Planner — port of the prototype's planner, made real:
   - start = the RM's current location (geolocation)
   - stops picked from LIVE inventory (geocoded lat/lng)
   - "Optimize route" reorders for the shortest trip regardless of pick order
   - Google Map draws the driving route via the Directions API
   - saves the plan to the lead */
import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useInventory, useAssignees, formatPrice } from "../lib/queries";
import { InventoryItem, api } from "../lib/api";
import { useToast } from "../components/Toast";
import { optimizeRoute, estimateLeg, pathKm, fmtMin, Pt } from "../lib/geo";
import { loadGoogleMaps, getCurrentLocation, openInMaps, MAPS_API_KEY } from "../lib/maps";
import { BookVisitsDrawer, BookUnit } from "./BookVisitsDrawer";

const today = () => new Date().toISOString().slice(0, 10);

export function VisitPlanner({ leadId, leadName, leadCity, onClose }: { leadId: string; leadName: string | null; leadCity: string | null; onClose: () => void }) {
  const { data: inv } = useInventory();
  const { data: assignees } = useAssignees();
  const toast = useToast();
  const qc = useQueryClient();

  const [start, setStart] = useState<Pt | null>(null);
  const [locating, setLocating] = useState(true);
  const [stopIds, setStopIds] = useState<number[]>([]);
  const [tripDate, setTripDate] = useState(today());
  const [rm, setRm] = useState("");
  const [saving, setSaving] = useState(false);
  const [googleMetrics, setGoogleMetrics] = useState<{ km: number; min: number } | null>(null);
  const [savedPlan, setSavedPlan] = useState(false); // unlocks the "Book on Openhouse" section
  const [booking, setBooking] = useState(false); // the booking drawer is open
  const [pickCity, setPickCity] = useState(leadCity || ""); // inventory city filter (defaults to lead's)
  const [societyQuery, setSocietyQuery] = useState(""); // society search — spans ALL cities

  const mapEl = useRef<HTMLDivElement>(null);
  const unlockEl = useRef<HTMLDivElement>(null);
  const mapObj = useRef<any>(null);
  const markers = useRef<any[]>([]);
  const dirRenderer = useRef<any>(null);

  const units = useMemo(() => (inv?.items ?? []).filter((u) => u.lat != null && u.lng != null), [inv]);
  const cities = useMemo(() => Array.from(new Set(units.map((u) => u.city).filter((c): c is string => !!c))).sort(), [units]);
  const sq = societyQuery.trim().toLowerCase();
  // society search spans ALL cities; otherwise filter by the chosen city
  const pickList = sq
    ? units.filter((u) => [u.society, u.name, u.locality].some((f) => (f || "").toLowerCase().includes(sq)))
    : pickCity
      ? units.filter((u) => u.city === pickCity)
      : units;
  const byId = (id: number) => units.find((u) => u.id === id);
  const stops = stopIds.map(byId).filter((u): u is InventoryItem => !!u);

  // estimate metrics (instant, haversine); replaced by Google driving values when available
  const est = useMemo(() => {
    const legs = stops.slice(1).map((s, i) => estimateLeg(stops[i] as Pt, s as Pt));
    const fromStart = start && stops.length ? estimateLeg(start, stops[0] as Pt) : null;
    const all = fromStart ? [fromStart, ...legs] : legs;
    return {
      legs,
      startLeg: fromStart,
      totalKm: +all.reduce((a, l) => a + l.km, 0).toFixed(1),
      totalMin: all.reduce((a, l) => a + l.min, 0),
    };
  }, [stopIds, start]);

  const total = googleMetrics
    ? { km: googleMetrics.km, min: googleMetrics.min, source: "google" as const }
    : { km: est.totalKm, min: est.totalMin, source: "est" as const };

  const locate = () => {
    setLocating(true);
    getCurrentLocation().then((loc) => {
      setStart(loc);
      setLocating(false);
      if (!loc) toast("📍 Allow location permission to optimize the route — then retry", "gold", "📍");
    });
  };
  useEffect(() => { locate(); }, []);

  useEffect(() => {
    if (rm === "" && assignees?.items.length) setRm(assignees.items[0].name);
  }, [assignees]);

  // init the map once
  useEffect(() => {
    if (!MAPS_API_KEY || !mapEl.current || mapObj.current) return;
    loadGoogleMaps()
      .then((g) => {
        mapObj.current = new g.maps.Map(mapEl.current!, {
          center: start || { lat: 28.46, lng: 77.05 }, zoom: 11,
          mapTypeControl: false, streetViewControl: false, fullscreenControl: false,
        });
        dirRenderer.current = new g.maps.DirectionsRenderer({
          map: mapObj.current, suppressMarkers: true,
          polylineOptions: { strokeColor: "#2563eb", strokeWeight: 5, strokeOpacity: 0.85 },
        });
        draw();
      })
      .catch((e) => toast(e.message, "gold", "⚠"));
  }, [mapEl.current]);

  // redraw whenever stops or start change
  useEffect(() => { draw(); }, [stopIds, start]);

  const draw = () => {
    const g = (window as any).google;
    if (!g || !mapObj.current) return;
    markers.current.forEach((m) => m.setMap(null));
    markers.current = [];
    setGoogleMetrics(null);
    const bounds = new g.maps.LatLngBounds();
    if (start) {
      markers.current.push(new g.maps.Marker({
        position: start, map: mapObj.current, title: "You (start)",
        label: { text: "A", color: "#fff", fontWeight: "700" },
        icon: { path: g.maps.SymbolPath.CIRCLE, scale: 9, fillColor: "#059669", fillOpacity: 1, strokeColor: "#fff", strokeWeight: 2 },
      }));
      bounds.extend(start);
    }
    stops.forEach((s, i) => {
      markers.current.push(new g.maps.Marker({
        position: { lat: s.lat!, lng: s.lng! }, map: mapObj.current,
        label: { text: String(i + 1), color: "#fff", fontWeight: "700" }, title: `Visit ${i + 1} · ${s.name}`,
      }));
      bounds.extend({ lat: s.lat!, lng: s.lng! });
    });
    if (dirRenderer.current) dirRenderer.current.set("directions", null);
    if (!stops.length) return;
    if (markers.current.length) mapObj.current.fitBounds(bounds, 60);

    const waypts = stops.slice(0, -1).map((s) => ({ location: { lat: s.lat!, lng: s.lng! }, stopover: true }));
    const origin = start || { lat: stops[0].lat!, lng: stops[0].lng! };
    const startIdx = start ? 0 : 1;
    new g.maps.DirectionsService().route(
      {
        origin,
        destination: { lat: stops[stops.length - 1].lat!, lng: stops[stops.length - 1].lng! },
        waypoints: start ? waypts : waypts.slice(1),
        travelMode: g.maps.TravelMode.DRIVING,
      },
      (res: any, status: string) => {
        if (status === "OK" && res.routes?.[0]) {
          dirRenderer.current.setDirections(res);
          const legs = res.routes[0].legs;
          const km = +(legs.reduce((a: number, l: any) => a + l.distance.value, 0) / 1000).toFixed(1);
          const min = Math.round(legs.reduce((a: number, l: any) => a + l.duration.value, 0) / 60);
          setGoogleMetrics({ km, min });
        }
        void startIdx;
      }
    );
  };

  const add = (id: number) => !stopIds.includes(id) && setStopIds([...stopIds, id]);
  const remove = (i: number) => setStopIds(stopIds.filter((_, idx) => idx !== i));
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= stopIds.length) return;
    const next = [...stopIds];
    [next[i], next[j]] = [next[j], next[i]];
    setStopIds(next);
  };

  const optimize = () => {
    if (!start) { toast("📍 Allow location permission to optimize the route from your location", "gold", "📍"); return; }
    if (stops.length < 2) { toast("Add 2+ stops to optimize", "gold", "⚠"); return; }
    const before = pathKm(start, stops as Pt[]);
    const ordered = optimizeRoute(start, stops as (InventoryItem & Pt)[]);
    setStopIds(ordered.map((u) => u.id));
    const after = pathKm(start, ordered as Pt[]);
    const saved = +(before - after).toFixed(1);
    toast(saved > 0.1 ? `Optimized · saved ~${saved} km` : "Already the shortest route", "green", "🧭");
  };

  const save = () => {
    if (!stops.length) { toast("Add at least one property", "gold", "⚠"); return; }
    setSaving(true);
    api.saveVisit(leadId, {
      trip_date: tripDate, rm, start_lat: start?.lat ?? null, start_lng: start?.lng ?? null,
      total_km: total.km, total_min: total.min, route_source: total.source,
      stops: stops.map((s) => ({ inventory_id: s.id, name: s.name, society: s.society, locality: s.locality, price_text: s.price_text, lat: s.lat, lng: s.lng })),
    })
      .then(() => {
        toast(`${stops.length}-stop visit plan saved`, "green", "✓");
        qc.invalidateQueries({ queryKey: ["lead", leadId] });
        qc.invalidateQueries({ queryKey: ["leads"] });
        qc.invalidateQueries({ queryKey: ["visit", leadId] });
        setSavedPlan(true); // don't close — reveal the "Book on Openhouse" section
      })
      .catch((e) => toast(e.message, "gold", "⚠"))
      .finally(() => setSaving(false));
  };

  // the "woosh": once the plan is saved, smoothly scroll the unlocked section into view
  useEffect(() => {
    if (!savedPlan) return;
    const t = setTimeout(() => unlockEl.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 90);
    return () => clearTimeout(t);
  }, [savedPlan]);

  // the just-planned stops, shaped for the booking drawer (home_id comes off the raw OH row)
  const bookUnits: BookUnit[] = stops.map((s) => ({
    homeId: (s.raw?.home_id as string | number) ?? s.id,
    name: s.name, society: s.society, locality: s.locality, city: s.city,
    configuration: s.configuration, priceText: s.price_text, priceLacs: s.price_lacs,
    status: /ready|available/i.test(s.status || "") ? "ready" : "coming_soon",
  }));

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal wide">
        <div className="mh">
          <h3>📅 Plan site visits · {leadName}</h3>
          <div className="icon-btn" onClick={onClose}>✕</div>
        </div>
        <div className="mb">
          <div className="note" style={{ marginBottom: 12 }}>
            Pick properties from live inventory as <b>Visit 1, 2, 3…</b> The route starts from{" "}
            <b>{locating ? "your location…" : start ? "your current location" : "(location unavailable)"}</b> and the map
            plots the optimized driving route.
          </div>
          {!locating && !start && (
            <div className="mand-flag show" style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 10 }}>
              <span>⚠ Location permission is off — allow it in your browser to optimize the route from your location.</span>
              <button className="btn ghost sm" onClick={locate}>📍 Allow / retry</button>
            </div>
          )}
          <div className="two">
            <div className="field" style={{ marginBottom: 12 }}><label>Trip date</label>
              <input type="date" value={tripDate} onChange={(e) => setTripDate(e.target.value)} /></div>
            <div className="field" style={{ marginBottom: 12 }}><label>RM accompanying</label>
              <select value={rm} onChange={(e) => setRm(e.target.value)}>
                {(assignees?.items ?? []).map((a) => <option key={a.email}>{a.name}</option>)}
                <option>Self</option>
              </select></div>
          </div>

          <div className="plan-cols">
            <div className="plan-pick">
              <div className="pick-head">
                <div className="plan-lbl"><span>Live inventory</span><span>{pickList.length} unit{pickList.length !== 1 ? "s" : ""}</span></div>
                <div style={{ display: "flex", gap: 6 }}>
                  <select className="pick-ctrl" value={pickCity} disabled={!!sq} onChange={(e) => setPickCity(e.target.value)} title={sq ? "Showing all cities while searching" : "Filter by city"}>
                    <option value="">All cities</option>
                    {cities.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <input className="pick-ctrl" style={{ flex: 1 }} value={societyQuery} placeholder="Search society — any city" onChange={(e) => setSocietyQuery(e.target.value)} />
                </div>
              </div>
              <div>
                {pickList.length === 0 ? (
                  <div className="itin-empty">{sq ? "No societies match." : "No geocoded inventory in this city."}</div>
                ) : pickList.map((p) => {
                  const added = stopIds.includes(p.id);
                  return (
                    <div key={p.id} className={"pick-row" + (added ? " added" : "")}>
                      <div style={{ minWidth: 0 }}>
                        <div className="pk-n">{p.name}</div>
                        <div className="pk-l">{[p.locality, p.city].filter(Boolean).join(", ")} · {formatPrice(p.price_lacs, p.price_text)} · {p.configuration || "—"}</div>
                      </div>
                      <button className={"btn sm pk-add " + (added ? "ghost" : "primary")} disabled={added} onClick={() => add(p.id)}>
                        {added ? "Added ✓" : "+ Add"}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="plan-itin">
              <div className="plan-lbl">
                <span>Itinerary</span>
                <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <button className="btn green sm opt-btn" disabled={stops.length < 2 || !start} onClick={optimize}>🧭 Optimize route</button>
                  <span>{stops.length} stop{stops.length !== 1 ? "s" : ""}</span>
                </span>
              </div>
              <div>
                {stops.length === 0 ? (
                  <div className="itin-empty">No stops yet.<br />Add properties from the left.</div>
                ) : stops.map((p, i) => {
                  const leg = i === 0 ? est.startLeg : est.legs[i - 1];
                  const legLabel = i === 0 ? "from your location" : "";
                  return (
                    <div key={p.id}>
                      {leg && <div className="leg"><span className="lp" />{leg.km} km · {fmtMin(leg.min)} {legLabel || "(est.)"}</div>}
                      <div className="itin-stop">
                        <div className="num">{i + 1}</div>
                        <div style={{ flex: 1, minWidth: 0 }}><div className="sn">Visit {i + 1} · {p.name}</div><div className="sl">{[p.locality, p.city].filter(Boolean).join(", ")}</div></div>
                        <div className="ops">
                          <button title="Up" onClick={() => move(i, -1)} disabled={i === 0}>↑</button>
                          <button title="Down" onClick={() => move(i, 1)} disabled={i === stops.length - 1}>↓</button>
                          <button title="Remove" onClick={() => remove(i)}>✕</button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              {stops.length >= 1 && (
                <div className="totals">
                  <div className="tbox"><div className="tv">{total.km} km</div><div className="tl">Total distance</div></div>
                  <div className="tbox"><div className="tv">{fmtMin(total.min)}</div><div className="tl">Drive time</div></div>
                  <div className="tbox"><div className="tv">{stops.length}</div><div className="tl">Stops</div></div>
                </div>
              )}
              {stops.length >= 1 && (
                <div className="route-est" style={total.source === "google" ? { color: "var(--emerald)" } : undefined}>
                  {total.source === "google" ? "✓ Live Google driving route" : "⚠ Straight-line estimate × road factor"}
                </div>
              )}
            </div>
          </div>

          <div className="plan-map" ref={mapEl}>
            {!MAPS_API_KEY && (
              <div className="map-empty">
                <div style={{ fontSize: 22 }}>🗺️</div>
                <div><b>Map needs a key.</b> Set <code>VITE_MAPS_API_KEY</code> to enable the live map &amp; route.</div>
                <div style={{ fontSize: 11 }}>The itinerary and distance estimates work without it.</div>
              </div>
            )}
          </div>

          {savedPlan && (
            <div className="bv-unlock" ref={unlockEl}>
              <div className="bv-unlock-head">
                <span className="bv-unlock-tick">✓</span>
                <div>
                  <div className="bv-unlock-title">Plan saved · ready to book on the Openhouse app</div>
                  <div className="bv-unlock-sub">Book these {stops.length} visit{stops.length !== 1 ? "s" : ""} for a Channel Partner — single or bulk, in one guided flow.</div>
                </div>
                <span className="bv-unlock-beta">Beta</span>
              </div>
              <div className="bv-unlock-grid">
                <div className="bv-ug-head">
                  <span>Unit</span><span>Home</span><span>Locality</span><span>Config</span><span>Ask</span><span>Status</span>
                </div>
                {bookUnits.map((u) => (
                  <div key={String(u.homeId)} className="bv-ug-row">
                    <span className="bv-ug-name">{u.name || u.society || "—"}{u.isNew && <span className="bv-newtag">NEW</span>}</span>
                    <span className="bv-ug-home">#{u.homeId}</span>
                    <span>{[u.locality, u.city].filter(Boolean).join(", ") || "—"}</span>
                    <span>{u.configuration || "—"}</span>
                    <span>{formatPrice(u.priceLacs, u.priceText)}</span>
                    <span><span className={"bv-pill " + (u.status === "ready" ? "ready" : "soon")}>{u.status === "ready" ? "Ready" : "Coming soon"}</span></span>
                  </div>
                ))}
              </div>
              <button className="btn orange bv-unlock-cta" onClick={() => setBooking(true)}>
                📲 Book {stops.length} visit{stops.length !== 1 ? "s" : ""} on Openhouse app
              </button>
            </div>
          )}
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>{savedPlan ? "Close" : "Cancel"}</button>
          <button className="btn ghost" disabled={!stops.length} onClick={() => openInMaps(start, stops)}>↗ Open in Google Maps</button>
          {!savedPlan && (
            <button className="btn green" onClick={save} disabled={saving || !stops.length}>{saving ? "Saving…" : "Save visit plan"}</button>
          )}
        </div>
      </div>
      {booking && <BookVisitsDrawer units={bookUnits} onClose={() => setBooking(false)} />}
    </div>
  );
}
