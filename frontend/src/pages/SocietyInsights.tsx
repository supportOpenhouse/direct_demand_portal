/**
 * Society Insights — demand (buyers) vs live supply (units) per society,
 * demand-gap flags and free-form buyer insights ("+ Add society insight").
 */
import { useState } from 'react';
import { EmptyState } from '../components/EmptyState';
import { KpiCard } from '../components/KpiCard';
import { Topbar } from '../components/Topbar';
import { IconFlame, IconInventory, IconLeads, IconSociety } from '../components/icons';
import { AddInsightModal } from '../features/modals/AddInsightModal';
import { useAddLeadModal } from '../features/modals/AddLeadModal';
import { ApiError } from '../lib/api';
import { timeAgo } from '../lib/format';
import { useSocietyInsights } from '../lib/queries';
import type { SocietyCard } from '../lib/types';

function errDetail(e: unknown): string {
  if (e instanceof ApiError) return e.detail;
  return e instanceof Error ? e.message : 'Something went wrong';
}

const MAX_INSIGHTS_SHOWN = 3;

function SocietyTile({
  card,
  onAddInsight,
}: {
  card: SocietyCard;
  onAddInsight: (society: string, city: string) => void;
}) {
  const total = card.buyers + card.live_units;
  const demandPct = total > 0 ? Math.round((card.buyers / total) * 100) : 0;
  const shown = card.insights.slice(0, MAX_INSIGHTS_SHOWN);
  const extra = card.insights.length - shown.length;

  return (
    <div className="card panel-pad">
      <div className="section-head" style={{ marginBottom: 10 }}>
        <div>
          <div style={{ fontFamily: "'Bricolage Grotesque',sans-serif", fontWeight: 700, fontSize: 15 }}>
            {card.society}
          </div>
          <div style={{ color: 'var(--muted)', fontSize: 12 }}>{card.city}</div>
        </div>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => onAddInsight(card.society, card.city)}
        >
          + Add
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>Buyers</div>
          <div style={{ fontFamily: "'Bricolage Grotesque',sans-serif", fontWeight: 700, fontSize: 18 }}>
            {card.buyers}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>Live units</div>
          <div style={{ fontFamily: "'Bricolage Grotesque',sans-serif", fontWeight: 700, fontSize: 18 }}>
            {card.live_units}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>Demand gap</div>
          <div
            style={{
              fontFamily: "'Bricolage Grotesque',sans-serif",
              fontWeight: 700,
              fontSize: 18,
              color: card.demand_gap > 0 ? 'var(--coral)' : undefined,
            }}
          >
            {card.demand_gap}
          </div>
        </div>
      </div>

      <div className="interest-bar" style={{ marginBottom: 10 }} title={`${demandPct}% demand vs supply`}>
        <span style={{ width: `${demandPct}%` }} />
      </div>

      {card.hot_buyers > 0 && (
        <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--coral)', marginBottom: 10 }}>
          🔥 {card.hot_buyers} immediate buyer{card.hot_buyers === 1 ? '' : 's'}
        </div>
      )}

      <div style={{ borderTop: '1px solid var(--line-2)', paddingTop: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>💡 Buyer insights</div>
        {shown.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>No insights yet — add what buyers ask about.</div>
        ) : (
          <>
            {shown.map((i) => (
              <div key={i.id} style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 12.5 }}>{i.note}</div>
                <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                  {i.created_by_name ?? 'Team'} · {timeAgo(i.created_at)}
                </div>
              </div>
            ))}
            {extra > 0 && <div style={{ fontSize: 11.5, color: 'var(--muted)' }}>+{extra} more</div>}
          </>
        )}
      </div>
    </div>
  );
}

export default function SocietyInsights() {
  const { openAddLead, addLeadModal } = useAddLeadModal();
  const { data, isLoading, error } = useSocietyInsights();
  const [insightModal, setInsightModal] = useState<{
    open: boolean;
    society?: string;
    city?: string;
  }>({ open: false });

  const openInsight = (society?: string, city?: string) =>
    setInsightModal({ open: true, society, city });

  return (
    <>
      <Topbar onAddLead={openAddLead} />
      <div className="view">
        <div className="section-head">
          <div>
            <div style={{ fontFamily: "'Bricolage Grotesque',sans-serif", fontWeight: 700, fontSize: 17 }}>
              Society Insights
            </div>
            <div style={{ color: 'var(--muted)', fontSize: 13 }}>
              Demand vs live supply per society — spot where to source next.
            </div>
          </div>
          <button type="button" className="btn gold" onClick={() => openInsight()}>
            + Add society insight
          </button>
        </div>

        {isLoading && <div className="empty">Loading…</div>}
        {error != null && <div className="note">{errDetail(error)}</div>}

        {data && (
          <>
            <div className="kpi-row" style={{ gridTemplateColumns: 'repeat(4,1fr)' }}>
              <KpiCard
                label="Societies tracked"
                value={data.stats.societies_tracked}
                accent="var(--gold)"
                soft="var(--gold-soft)"
                icon={<IconSociety size={16} />}
              />
              <KpiCard
                label="Total demand"
                value={data.stats.total_demand}
                accent="var(--blue)"
                soft="var(--blue-soft)"
                icon={<IconLeads size={16} />}
              />
              <KpiCard
                label="Live units"
                value={data.stats.live_units}
                accent="var(--emerald)"
                soft="var(--emerald-soft)"
                icon={<IconInventory size={16} />}
              />
              <KpiCard
                label="High-demand gaps"
                value={data.stats.high_demand_gaps}
                accent="var(--coral)"
                soft="var(--coral-soft)"
                icon={<IconFlame size={16} />}
              />
            </div>

            {data.societies.length === 0 ? (
              <EmptyState msg="No societies tracked yet — add a society insight to get started." />
            ) : (
              <div className="grid-3" style={{ alignItems: 'start' }}>
                {data.societies.map((s) => (
                  <SocietyTile key={`${s.society}|${s.city}`} card={s} onAddInsight={openInsight} />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <AddInsightModal
        open={insightModal.open}
        onClose={() => setInsightModal((m) => ({ ...m, open: false }))}
        defaultSociety={insightModal.society}
        defaultCity={insightModal.city}
      />
      {addLeadModal}
    </>
  );
}
