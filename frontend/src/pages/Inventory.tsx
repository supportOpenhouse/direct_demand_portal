/**
 * Live Inventory — 3-col grid of acquired, ready-to-transact property cards
 * synced from the Acquired Property Dashboard.
 */
import { useState } from 'react';
import { EmptyState } from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { Topbar } from '../components/Topbar';
import { useAddLeadModal } from '../features/modals/AddLeadModal';
import { ApiError } from '../lib/api';
import { budgetLabel, formatLacs } from '../lib/format';
import { useInventory } from '../lib/queries';
import type { Unit } from '../lib/types';

const EXT_SOURCE_LABELS: Record<Unit['ext_source'], string> = {
  acquired_property: 'Acquired Property Dashboard',
  supply_tracker: 'Supply Closure Tracker',
};

function statusChipStyle(status: string | null): React.CSSProperties {
  const available = (status ?? '').toLowerCase() === 'available';
  return available
    ? { background: 'var(--emerald-soft)', color: 'var(--emerald)', borderColor: 'transparent' }
    : { background: 'var(--amber-soft)', color: 'var(--amber)', borderColor: 'transparent' };
}

function locationLine(u: Unit): string {
  const parts = [u.society, u.city].filter(Boolean);
  return parts.length ? `📍 ${parts.join(', ')}` : '📍 —';
}

function InventoryCard({ unit }: { unit: Unit }) {
  const { push } = useToast();
  const [open, setOpen] = useState(false);

  return (
    <div className="card">
      {unit.image_url ? (
        <img
          src={unit.image_url}
          alt={unit.name}
          style={{ width: '100%', height: 150, objectFit: 'cover', display: 'block' }}
        />
      ) : (
        <div className="thumb-ph" style={{ width: '100%', height: 150 }} />
      )}
      <div className="panel-pad">
        <div style={{ marginBottom: 8 }}>
          <span
            className="chip"
            style={{ textTransform: 'uppercase', letterSpacing: '.05em', ...statusChipStyle(unit.status) }}
          >
            {unit.status ?? 'available'}
          </span>
        </div>
        <div style={{ fontWeight: 600, fontSize: 14 }}>{unit.name}</div>
        <div style={{ color: 'var(--muted)', fontSize: 12.5, marginTop: 2 }}>{locationLine(unit)}</div>
        <div
          style={{
            fontFamily: "'Bricolage Grotesque', sans-serif",
            fontSize: 18,
            fontWeight: 700,
            margin: '8px 0',
          }}
        >
          {formatLacs(unit.price_lacs)}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          {unit.configuration && <span className="chip">{unit.configuration}</span>}
          {unit.area_sqft !== null && <span className="chip">{unit.area_sqft} sq.ft</span>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            className="btn sm wa"
            onClick={() => push({ kind: 'wa', title: 'Brochure shared on WhatsApp' })}
          >
            Share
          </button>
          <button type="button" className="btn sm ghost" onClick={() => setOpen((v) => !v)}>
            Details
          </button>
        </div>
        {open && (
          <div className="opt-dl" style={{ marginTop: 12, marginBottom: 0 }}>
            <div>
              <div className="k">Budget band</div>
              <div className="v">{budgetLabel(unit.budget_min_lacs, unit.budget_max_lacs)}</div>
            </div>
            <div>
              <div className="k">Source</div>
              <div className="v">{EXT_SOURCE_LABELS[unit.ext_source]}</div>
            </div>
            <div>
              <div className="k">Status</div>
              <div className="v" style={{ textTransform: 'capitalize' }}>
                {unit.status ?? '—'}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Inventory() {
  const { openAddLead, addLeadModal } = useAddLeadModal();
  const { data: units, isLoading, error } = useInventory();

  return (
    <>
      <Topbar title="Live Inventory" onAddLead={openAddLead} />
      <div className="view">
        <div className="page-sub">
          Acquired, ready-to-transact units synced from the Acquired Property Dashboard.
        </div>
        {isLoading && <div className="empty">Loading…</div>}
        {error && (
          <div className="note">
            {error instanceof ApiError ? error.detail : 'Failed to load inventory.'}
          </div>
        )}
        {units &&
          (units.length === 0 ? (
            <EmptyState msg="No live inventory yet." />
          ) : (
            <div className="grid-3">
              {units.map((u) => (
                <InventoryCard key={u.id} unit={u} />
              ))}
            </div>
          ))}
      </div>
      {addLeadModal}
    </>
  );
}
