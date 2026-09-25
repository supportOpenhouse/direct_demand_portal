/* Visit Planner — pick units from LIVE inventory, then book them on Openhouse.
   No map, no route, no location: BOOK VISITS hands the selection straight to the
   booking drawer (slot + buyer). RM accompanying lists every active non-admin user and
   defaults to the lead's owner; one without an SMID gets the drawer's "no SMID" warning. */
import { useMemo, useState } from "react";
import { useInventory, useLead, useAssignees, formatPrice } from "../lib/queries";
import { next7Days } from "../lib/slots";
import { InventoryItem } from "../lib/api";
import { BookVisitsDrawer, BookUnit } from "./BookVisitsDrawer";
import { IconCalendar, IconCheck, IconX } from "../components/icons";

export function VisitPlanner({ leadId, leadName, leadCity, leadPhone, onClose }: { leadId: string; leadName: string | null; leadCity: string | null; leadPhone?: string | null; onClose: () => void }) {
  const { data: inv } = useInventory();
  const { data: lead } = useLead(leadId);
  const { data: assignees } = useAssignees();
  const rms = assignees?.items ?? [];

  const [stopIds, setStopIds] = useState<number[]>([]);
  // the drawer books within the next 7 days, so the date is capped to that window
  const days = useMemo(() => next7Days(), []);
  const [tripDate, setTripDate] = useState(days[0].date);
  const [booking, setBooking] = useState(false); // the booking drawer is open
  const [dragId, setDragId] = useState<number | null>(null); // the row being dragged
  const [pickCity, setPickCity] = useState(leadCity || ""); // inventory city filter (defaults to lead's)
  const [societyQuery, setSocietyQuery] = useState(""); // society search — within the selected city

  const [rmPick, setRmPick] = useState<string | null>(null); // null = still following the lead's owner
  const rmAccompanying = rmPick ?? lead?.assigned_to ?? "";

  const units = useMemo(() => inv?.items ?? [], [inv]);
  const cities = useMemo(() => Array.from(new Set(units.map((u) => u.city).filter((c): c is string => !!c))).sort(), [units]);
  const sq = societyQuery.trim().toLowerCase();
  // scope to the chosen city first, then filter by the society search within it
  const inCity = pickCity ? units.filter((u) => u.city === pickCity) : units;
  const pickList = sq
    ? inCity.filter((u) => [u.society, u.name, u.locality].some((f) => (f || "").toLowerCase().includes(sq)))
    : inCity;
  const stops = stopIds.map((id) => units.find((u) => u.id === id)).filter((u): u is InventoryItem => !!u);

  const add = (id: number) => !stopIds.includes(id) && setStopIds([...stopIds, id]);
  const remove = (i: number) => setStopIds(stopIds.filter((_, idx) => idx !== i));
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= stopIds.length) return;
    const next = [...stopIds];
    [next[i], next[j]] = [next[j], next[i]];
    setStopIds(next);
  };
  // native HTML5 drag: the dragged row moves live into whichever row it's over
  const dragOver = (e: React.DragEvent, overId: number) => {
    e.preventDefault();
    if (dragId == null || dragId === overId) return;
    const next = stopIds.filter((id) => id !== dragId);
    next.splice(stopIds.indexOf(overId), 0, dragId);
    setStopIds(next);
  };

  // the selected units, shaped for the booking drawer (home_id comes off the raw OH row)
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
          <h3><IconCalendar /> Plan site visits · {leadName}</h3>
          <div className="icon-btn" onClick={onClose}><IconX /></div>
        </div>
        <div className="mb">
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <div className="field" style={{ marginBottom: 12, width: 200 }}><label>Trip date</label>
            <input type="date" value={tripDate} min={days[0].date} max={days[days.length - 1].date}
              onChange={(e) => e.target.value && setTripDate(e.target.value)} /></div>
            <div className="field" style={{ marginBottom: 12, width: 260 }}><label>RM accompanying</label>
              <select value={rmAccompanying} onChange={(e) => setRmPick(e.target.value)}>
                {!rmAccompanying && <option value="">Select RM…</option>}
                {rms.map((r) => <option key={r.email} value={r.name}>{r.name}{r.smid == null ? " (no SMID)" : ""}</option>)}
              </select></div>
          </div>

          <div className="plan-cols">
            <div className="plan-pick">
              <div className="pick-head">
                <div className="plan-lbl"><span>Live inventory</span><span>{pickList.length} unit{pickList.length !== 1 ? "s" : ""}</span></div>
                <div style={{ display: "flex", gap: 6 }}>
                  <select className="pick-ctrl" value={pickCity} onChange={(e) => setPickCity(e.target.value)} title="Filter by city">
                    <option value="">All cities</option>
                    {cities.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <input className="pick-ctrl" style={{ flex: 1 }} value={societyQuery} placeholder="Search society in this city" onChange={(e) => setSocietyQuery(e.target.value)} />
                </div>
              </div>
              <div>
                {pickList.length === 0 ? (
                  <div className="itin-empty">{sq ? "No societies match." : "No inventory in this city."}</div>
                ) : pickList.map((p) => {
                  const added = stopIds.includes(p.id);
                  return (
                    <div key={p.id} className={"pick-row" + (added ? " added" : "")}>
                      <div style={{ minWidth: 0 }}>
                        <div className="pk-n">{p.name}</div>
                        <div className="pk-l">{[p.locality, p.city].filter(Boolean).join(", ")} · {formatPrice(p.price_lacs, p.price_text)} · {p.configuration || "—"}</div>
                      </div>
                      <button className={"btn sm pk-add " + (added ? "ghost" : "primary")} disabled={added} onClick={() => add(p.id)}>
                        {added ? <><IconCheck /> Added</> : "+ Add"}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="plan-itin">
              <div className="plan-lbl">
                <span>Selected inventory</span>
                <span>{stops.length} selected</span>
              </div>
              <div>
                {stops.length === 0 ? (
                  <div className="itin-empty">Nothing selected yet.<br />Add properties from the left.</div>
                ) : stops.map((p, i) => (
                  <div key={p.id} className={"itin-stop" + (dragId === p.id ? " dragging" : "")} draggable
                    onDragStart={(e) => { setDragId(p.id); e.dataTransfer.effectAllowed = "move"; }}
                    onDragOver={(e) => dragOver(e, p.id)} onDrop={(e) => e.preventDefault()} onDragEnd={() => setDragId(null)}>
                    <div className="num">{i + 1}</div>
                    <div style={{ flex: 1, minWidth: 0 }}><div className="sn">Visit {i + 1} · {p.name}</div><div className="sl">{[p.locality, p.city].filter(Boolean).join(", ")}</div></div>
                    <div className="ops">
                      <button title="Up" onClick={() => move(i, -1)} disabled={i === 0}>↑</button>
                      <button title="Down" onClick={() => move(i, 1)} disabled={i === stops.length - 1}>↓</button>
                      <button title="Remove" onClick={() => remove(i)}><IconX /></button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn orange" onClick={() => setBooking(true)} disabled={!stops.length || !rmAccompanying}>BOOK VISITS</button>
        </div>
      </div>
      {booking && <BookVisitsDrawer units={bookUnits} leadId={leadId} leadName={leadName} leadPhone={leadPhone} initialDate={tripDate}
        salesManagerId={rms.find((r) => r.name === rmAccompanying)?.smid ?? null}
        rmAccompanying={rmAccompanying || undefined} onClose={() => setBooking(false)} />}
    </div>
  );
}
