/**
 * Supply Pipeline — 3-col grid of MSI / token-paid / negotiating units from the
 * Supply Closure Tracker; tag buyer interest before units land.
 */
import { EmptyState } from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { Topbar } from '../components/Topbar';
import { useAddLeadModal } from '../features/modals/AddLeadModal';
import { ApiError } from '../lib/api';
import { formatDate, formatLacs } from '../lib/format';
import { useAddInterest, useSupply } from '../lib/queries';
import type { SupplyStage, Unit } from '../lib/types';

const STAGE_META: Record<SupplyStage, { label: string; bg: string; fg: string }> = {
  msi: { label: 'MSI', bg: 'var(--blue-soft)', fg: 'var(--blue)' },
  token_paid: { label: 'Token paid', bg: 'var(--amber-soft)', fg: 'var(--amber)' },
  negotiating: { label: 'Negotiating', bg: 'var(--indigo-soft)', fg: 'var(--indigo)' },
};

function etaLabel(eta: string | null): string {
  if (!eta) return '—';
  return /^\d{4}-\d{2}-\d{2}/.test(eta) ? formatDate(eta) : eta;
}

function locationLine(u: Unit): string {
  const parts = [u.society, u.city].filter(Boolean);
  return parts.length ? `📍 ${parts.join(', ')}` : '📍 —';
}

function SupplyCard({ unit }: { unit: Unit }) {
  const { push } = useToast();
  const addInterest = useAddInterest();
  const stage = unit.supply_stage ? STAGE_META[unit.supply_stage] : null;
  const barPct = Math.min(unit.interest_count * 10, 100);

  const tagBuyer = () => {
    addInterest.mutate(
      { id: unit.id },
      {
        onSuccess: () => push({ kind: 'gold', title: 'Interest tagged' }),
        onError: (err) =>
          push({
            kind: 'blue',
            title: 'Could not tag interest',
            sub: err instanceof ApiError ? err.detail : undefined,
          }),
      },
    );
  };

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
        {stage && (
          <div style={{ marginBottom: 8 }}>
            <span
              className="chip"
              style={{
                textTransform: 'uppercase',
                letterSpacing: '.05em',
                background: stage.bg,
                color: stage.fg,
                borderColor: 'transparent',
              }}
            >
              {stage.label}
            </span>
          </div>
        )}
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
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
          {unit.configuration && <span className="chip">{unit.configuration}</span>}
          {unit.area_sqft !== null && <span className="chip">{unit.area_sqft} sq.ft</span>}
        </div>
        <div style={{ color: 'var(--muted)', fontSize: 12.5, marginBottom: 10 }}>
          🗓 Landing: {etaLabel(unit.eta)}
        </div>
        <div style={{ marginBottom: 12 }}>
          <div className="interest-bar">
            <span style={{ width: `${barPct}%` }} />
          </div>
          <div style={{ color: 'var(--muted)', fontSize: 11.5, marginTop: 4 }}>
            {unit.interest_count} buyer interests
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            className="btn sm gold"
            onClick={tagBuyer}
            disabled={addInterest.isPending}
          >
            🙋 I have a buyer
          </button>
          <button
            type="button"
            className="btn sm ghost"
            onClick={() => push({ kind: 'blue', title: "We'll notify you when this unit lands" })}
          >
            Notify on landing
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Supply() {
  const { openAddLead, addLeadModal } = useAddLeadModal();
  const { data: units, isLoading, error } = useSupply();

  return (
    <>
      <Topbar title="Supply Pipeline" onAddLead={openAddLead} />
      <div className="view">
        <div className="page-sub">
          MSI / token-paid / negotiating units from the Supply Closure Tracker — tag buyer
          interest early.
        </div>
        {isLoading && <div className="empty">Loading…</div>}
        {error && (
          <div className="note">
            {error instanceof ApiError ? error.detail : 'Failed to load supply pipeline.'}
          </div>
        )}
        {units &&
          (units.length === 0 ? (
            <EmptyState msg="No supply units in the pipeline yet." />
          ) : (
            <div className="grid-3">
              {units.map((u) => (
                <SupplyCard key={u.id} unit={u} />
              ))}
            </div>
          ))}
      </div>
      {addLeadModal}
    </>
  );
}
