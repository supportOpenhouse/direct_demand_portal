/**
 * Visit Planner — wide modal for building a multi-stop visit itinerary for a lead.
 * Left: city-filtered inventory picker. Right: ordered Visit 1/2/3… itinerary with
 * per-leg estimates, reorder/remove, totals and one-click route optimisation.
 * Below: full-width map (numbered pins + route). Save creates the visit via the API.
 */
import { useEffect, useMemo, useState } from 'react';
import { Modal } from '../../components/Modal';
import { EmptyState } from '../../components/EmptyState';
import { useToast } from '../../components/Toast';
import { useAuth } from '../../store/auth';
import { useCreateVisit, useInventory } from '../../lib/queries';
import { ApiError } from '../../lib/api';
import { formatLacs } from '../../lib/format';
import type { LeadRow, Unit } from '../../lib/types';
import { legEstimate, optimizeRoute, routeTotals } from './optimizer';
import { MapCanvas } from './MapCanvas';

/** A unit that made it into the itinerary — guaranteed coordinates. */
interface PlannedStop {
  unit: Unit;
  lat: number;
  lng: number;
}

function todayStr(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function errorDetail(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return 'Something went wrong';
}

export function VisitPlannerModal({
  lead,
  onClose,
}: {
  lead: LeadRow | null;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const { push } = useToast();
  const inventory = useInventory();
  const createVisit = useCreateVisit(lead?.id ?? '');

  const [tripDate, setTripDate] = useState<string>(todayStr);
  const [stops, setStops] = useState<PlannedStop[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Fresh planner whenever a different lead is opened.
  useEffect(() => {
    setTripDate(todayStr());
    setStops([]);
    setSaveError(null);
  }, [lead?.id]);

  const units = useMemo(() => {
    const all = inventory.data ?? [];
    if (!lead?.city) return all;
    return all.filter((u) => u.city === lead.city);
  }, [inventory.data, lead?.city]);

  const totals = routeTotals(stops);

  if (!lead) return null;

  const addStop = (u: Unit) => {
    const lat = u.lat;
    const lng = u.lng;
    if (lat == null || lng == null) return;
    setStops((prev) =>
      prev.some((s) => s.unit.id === u.id) ? prev : [...prev, { unit: u, lat, lng }],
    );
  };

  const removeStop = (idx: number) => {
    setStops((prev) => prev.filter((_, i) => i !== idx));
  };

  const moveStop = (idx: number, dir: -1 | 1) => {
    setStops((prev) => {
      const j = idx + dir;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  };

  const handleOptimize = () => {
    const res = optimizeRoute(stops);
    setStops(res.order);
    if (res.savedKm > 0) {
      push({
        kind: 'gold',
        title: 'Route optimized',
        sub: `Saved ${res.savedKm} km · ${res.savedMin} min`,
      });
    } else {
      push({ kind: 'gold', title: 'Already optimal' });
    }
  };

  const handleSave = async () => {
    if (stops.length === 0 || createVisit.isPending) return;
    setSaveError(null);
    try {
      await createVisit.mutateAsync({
        trip_date: tripDate,
        stops: stops.map((s, i) => ({ inventory_id: s.unit.id, seq: i + 1 })),
        total_km: Math.round(totals.km * 10) / 10,
        total_min: Math.round(totals.min),
        route_source: 'est',
      });
      push({ kind: 'green', title: 'Visit scheduled', sub: '+2h feedback reminder created' });
      onClose();
    } catch (err) {
      setSaveError(errorDetail(err));
    }
  };

  return (
    <Modal
      wide
      open
      title={`Plan visits — ${lead.name}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn green"
            disabled={stops.length === 0 || createVisit.isPending}
            onClick={handleSave}
          >
            {createVisit.isPending ? 'Saving…' : 'Save itinerary'}
          </button>
        </>
      }
    >
      {/* header row: trip date + RM + city */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, marginBottom: 16 }}>
        <div className="field" style={{ marginBottom: 0, width: 180 }}>
          <label htmlFor="vp-trip-date">Trip date</label>
          <input
            id="vp-trip-date"
            type="date"
            value={tripDate}
            onChange={(e) => setTripDate(e.target.value)}
          />
        </div>
        <div style={{ flex: 1, fontSize: 12.5, color: 'var(--ink-2)', paddingBottom: 9 }}>
          <span style={{ color: 'var(--muted)', fontWeight: 600 }}>RM&nbsp;</span>
          <strong>{user?.name ?? '—'}</strong>
        </div>
        <span className="chip" style={{ marginBottom: 7 }}>
          {lead.city ?? 'City unknown'}
        </span>
      </div>

      {/* two-column body: picker | itinerary */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 16 }}>
        {/* LEFT — inventory picker */}
        <div className="card panel-pad" style={{ minWidth: 0 }}>
          <div className="panel-title" style={{ marginBottom: 10 }}>
            Inventory{lead.city ? ` — ${lead.city}` : ''}
          </div>
          {inventory.isLoading && <div className="note">Loading inventory…</div>}
          {inventory.error != null && <div className="note">{errorDetail(inventory.error)}</div>}
          {!inventory.isLoading && inventory.error == null && units.length === 0 && (
            <EmptyState msg={lead.city ? `No inventory in ${lead.city}` : 'No inventory yet'} />
          )}
          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            {units.map((u) => {
              const added = stops.some((s) => s.unit.id === u.id);
              const noLocation = u.lat == null || u.lng == null;
              return (
                <div key={u.id} className="opt">
                  <div className="opt-row" style={{ cursor: 'default' }}>
                    {u.image_url ? (
                      <img className="thumb" src={u.image_url} alt="" />
                    ) : (
                      <span className="thumb thumb-ph" />
                    )}
                    <div className="opt-info">
                      <div className="o-name">{u.name}</div>
                      <div className="o-meta">
                        {u.society ?? '—'} · {formatLacs(u.price_lacs)}
                        {noLocation && ' · (no location)'}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn sm ghost"
                      disabled={added || noLocation}
                      onClick={() => addStop(u)}
                    >
                      {added ? 'Added' : 'Add'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT — itinerary */}
        <div className="card panel-pad" style={{ minWidth: 0 }}>
          <div className="section-head" style={{ marginBottom: 10 }}>
            <div className="panel-title">Itinerary</div>
            <button
              type="button"
              className="btn sm gold"
              disabled={stops.length < 2}
              onClick={handleOptimize}
            >
              🧭 Optimize route
            </button>
          </div>

          {stops.length === 0 && <EmptyState msg="Add properties from the left to plan the trip" />}

          {stops.map((s, i) => {
            const leg = i > 0 ? legEstimate(stops[i - 1], s) : null;
            return (
              <div key={s.unit.id}>
                {leg && (
                  <div
                    className="mono"
                    style={{ fontSize: 11, color: 'var(--muted)', padding: '3px 0 3px 12px' }}
                  >
                    ↓ {leg.km} km · {leg.min} min
                  </div>
                )}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '8px 0',
                    borderBottom: '1px solid var(--line-2)',
                  }}
                >
                  <span className="chip">Visit {i + 1}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {s.unit.name}
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--muted)' }}>
                      {s.unit.society ?? '—'}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn sm ghost"
                    aria-label={`Move visit ${i + 1} up`}
                    disabled={i === 0}
                    onClick={() => moveStop(i, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="btn sm ghost"
                    aria-label={`Move visit ${i + 1} down`}
                    disabled={i === stops.length - 1}
                    onClick={() => moveStop(i, 1)}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="btn sm ghost"
                    aria-label={`Remove visit ${i + 1}`}
                    onClick={() => removeStop(i)}
                  >
                    ✕
                  </button>
                </div>
              </div>
            );
          })}

          {stops.length > 0 && (
            <div
              style={{
                display: 'flex',
                gap: 6,
                marginTop: 12,
                fontSize: 12.5,
                fontWeight: 600,
                color: 'var(--ink-2)',
              }}
            >
              <span>Total:</span>
              <span className="mono">
                {totals.km} km · {totals.min} min
              </span>
              <span style={{ color: 'var(--muted)' }}>
                · {stops.length} {stops.length === 1 ? 'stop' : 'stops'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* full-width map */}
      <div style={{ marginTop: 16 }}>
        <MapCanvas
          stops={stops.map((s) => ({ lat: s.lat, lng: s.lng, name: s.unit.name }))}
          height={300}
        />
      </div>

      {saveError && (
        <div className="note" style={{ marginTop: 12, color: 'var(--coral)' }}>
          {saveError}
        </div>
      )}
    </Modal>
  );
}
