/**
 * Gold Mine — auto-bucketing of every lead (active + dormant) against new
 * inventory, with bulk WhatsApp / push-to-call actions per bucket and a
 * deduped "All leads & their requirements" table.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Avatar } from '../components/Avatar';
import { EmptyState } from '../components/EmptyState';
import { StageChip } from '../components/StageChip';
import { PlanChip } from '../components/PlanChip';
import { Topbar } from '../components/Topbar';
import { useToast } from '../components/Toast';
import { useAddLeadModal } from '../features/modals/AddLeadModal';
import { ApiError } from '../lib/api';
import { useBroadcast, useBuckets, useRematch } from '../lib/queries';
import type { Bucket, LeadRow, MatchedOn } from '../lib/types';

function errDetail(e: unknown): string {
  if (e instanceof ApiError) return e.detail;
  return e instanceof Error ? e.message : 'Something went wrong';
}

const MATCHED_ON_LABELS: Record<MatchedOn, string> = {
  city: 'City',
  society: 'Society',
  budget: 'Budget',
  config: 'Config',
};

const COLLAPSE_AT = 5;

function BucketCard({ bucket }: { bucket: Bucket }) {
  const [showAll, setShowAll] = useState(false);
  const { push } = useToast();
  const broadcast = useBroadcast();

  const members = showAll ? bucket.members : bucket.members.slice(0, COLLAPSE_AT);
  const hidden = bucket.members.length - COLLAPSE_AT;

  const fire = async (mode: 'whatsapp' | 'call_list') => {
    try {
      const res = await broadcast.mutateAsync({ id: bucket.id, mode });
      if (mode === 'whatsapp') {
        push({ kind: 'wa', title: `Sent to ${res.sent} leads`, sub: bucket.unit.name });
      } else {
        push({ kind: 'green', title: `Pushed ${res.sent} leads to call list`, sub: bucket.unit.name });
      }
    } catch (e) {
      push({ kind: 'blue', title: 'Broadcast failed', sub: errDetail(e) });
    }
  };

  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '14px 18px',
          borderBottom: '1px solid var(--line-2)',
        }}
      >
        {bucket.unit.image_url ? (
          <img
            src={bucket.unit.image_url}
            alt={bucket.unit.name}
            style={{ width: 64, height: 64, borderRadius: 10, objectFit: 'cover', flex: '0 0 auto' }}
          />
        ) : (
          <span className="thumb-ph" style={{ width: 64, height: 64, borderRadius: 10, flex: '0 0 auto' }} />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: "'Bricolage Grotesque',sans-serif", fontWeight: 700, fontSize: 15 }}>
            {bucket.unit.name}
          </div>
          <div style={{ color: 'var(--muted)', fontSize: 12.5 }}>
            {[bucket.unit.society, bucket.unit.city].filter(Boolean).join(' · ') || '—'}
          </div>
        </div>
        <span
          className="chip"
          style={{ textTransform: 'uppercase', fontSize: 10.5, letterSpacing: '.05em', color: 'var(--ink-2)' }}
        >
          {bucket.unit_kind}
        </span>
        <span className="badge gold" style={{ marginLeft: 0 }}>
          {bucket.member_count} leads
        </span>
      </div>

      {members.map((m) => (
        <div
          key={m.lead.id}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 18px',
            borderBottom: '1px solid var(--line-2)',
          }}
        >
          <Avatar name={m.lead.name} size={28} />
          <Link
            to={`/leads/${m.lead.id}`}
            style={{ fontWeight: 600, color: 'inherit', textDecoration: 'none', whiteSpace: 'nowrap' }}
          >
            {m.lead.name}
            {m.lead.is_hot && ' 🔥'}
          </Link>
          <StageChip stage={m.lead.stage} />
          <span style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginLeft: 'auto' }}>
            {m.matched_on.map((mo) => (
              <span key={mo} className="chip" style={{ fontSize: 10.5, padding: '2px 7px' }}>
                {MATCHED_ON_LABELS[mo]}
              </span>
            ))}
          </span>
          <span className="mono" style={{ fontSize: 12, fontWeight: 600, color: 'var(--gold)', flex: '0 0 auto' }}>
            {m.match_pct}%
          </span>
        </div>
      ))}

      {hidden > 0 && (
        <button
          type="button"
          className="btn ghost sm"
          style={{ margin: '10px 18px 0' }}
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll ? 'Show fewer' : `Show all ${bucket.members.length} leads`}
        </button>
      )}

      <div style={{ display: 'flex', gap: 8, padding: '12px 18px' }}>
        <button
          type="button"
          className="btn wa sm"
          disabled={broadcast.isPending}
          onClick={() => fire('whatsapp')}
        >
          WhatsApp all ({bucket.member_count})
        </button>
        <button
          type="button"
          className="btn ghost sm"
          disabled={broadcast.isPending}
          onClick={() => fire('call_list')}
        >
          Push to call list
        </button>
      </div>
    </div>
  );
}

export default function GoldMine() {
  const { openAddLead, addLeadModal } = useAddLeadModal();
  const { data: buckets, isLoading, error } = useBuckets();
  const rematch = useRematch();
  const { push } = useToast();

  const runRematch = async () => {
    try {
      const res = await rematch.mutateAsync();
      push({ kind: 'gold', title: `Rebuilt ${res.buckets} buckets` });
    } catch (e) {
      push({ kind: 'blue', title: 'Rematch failed', sub: errDetail(e) });
    }
  };

  // Dedupe every bucket member by lead id + count how many buckets they sit in.
  const byLead = new Map<string, { lead: LeadRow; bucketCount: number }>();
  for (const b of buckets ?? []) {
    for (const m of b.members) {
      const entry = byLead.get(m.lead.id);
      if (entry) entry.bucketCount += 1;
      else byLead.set(m.lead.id, { lead: m.lead, bucketCount: 1 });
    }
  }
  const allLeads = [...byLead.values()];

  return (
    <>
      <Topbar onAddLead={openAddLead} />
      <div className="view">
        <div
          className="card panel-pad"
          style={{
            background: 'var(--gold-soft)',
            borderColor: 'var(--gold)',
            display: 'flex',
            alignItems: 'center',
            gap: 14,
            marginBottom: 16,
          }}
        >
          <div style={{ flex: 1, fontWeight: 600, color: 'var(--ink-2)' }}>
            ⛏ New inventory lands → every lead (active + dormant) is auto-bucketed against it
          </div>
          <button type="button" className="btn gold" disabled={rematch.isPending} onClick={runRematch}>
            {rematch.isPending ? 'Rematching…' : 'Rematch all'}
          </button>
        </div>

        {isLoading && <div className="empty">Loading…</div>}
        {error != null && <div className="note">{errDetail(error)}</div>}

        {buckets &&
          (buckets.length === 0 ? (
            <EmptyState msg="No buckets yet — run a rematch after adding inventory." />
          ) : (
            <>
              {buckets.map((b) => (
                <BucketCard key={b.id} bucket={b} />
              ))}

              <div className="card" style={{ marginTop: 4 }}>
                <div className="panel-pad" style={{ paddingBottom: 0 }}>
                  <div className="panel-title">All leads &amp; their requirements</div>
                </div>
                <div style={{ padding: '0 18px 14px' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        <th>Lead</th>
                        <th>City</th>
                        <th>Config</th>
                        <th>Budget</th>
                        <th>Plan</th>
                        <th>Bucketed in</th>
                      </tr>
                    </thead>
                    <tbody>
                      {allLeads.map(({ lead, bucketCount }) => (
                        <tr key={lead.id}>
                          <td>
                            <span className="who">
                              <Avatar name={lead.name} />
                              <span>
                                <span className="w-name">
                                  {lead.name}
                                  {lead.is_hot && ' 🔥'}
                                </span>
                                <br />
                                <span className="w-ph">{lead.phone}</span>
                              </span>
                            </span>
                          </td>
                          <td>{lead.city ?? '—'}</td>
                          <td>{lead.configuration ? <span className="chip">{lead.configuration}</span> : '—'}</td>
                          <td>{lead.budget_label ?? '—'}</td>
                          <td>
                            <PlanChip plan={lead.plan_to_buy} />
                          </td>
                          <td>
                            <span className="badge soft" style={{ marginLeft: 0 }}>
                              {bucketCount} bucket{bucketCount === 1 ? '' : 's'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ))}
      </div>
      {addLeadModal}
    </>
  );
}
