/**
 * Lead Details — /leads/:id. Two-layer data model:
 * LEFT  source-captured card (admin-edit) → confirmed-on-call Q1–Q6 → Activity
 * RIGHT top-5 inventory matches → top-5 supply matches → visit recordings.
 */
import { useNavigate, useParams } from 'react-router-dom';
import { Avatar } from '../components/Avatar';
import { SrcBadge } from '../components/SrcBadge';
import { StageChip } from '../components/StageChip';
import { TatChip } from '../components/TatChip';
import { Topbar } from '../components/Topbar';
import { IconFlame } from '../components/icons';
import { useToast } from '../components/Toast';
import { ActivityTimeline } from '../features/leadDetail/ActivityTimeline';
import { ConfirmForm } from '../features/leadDetail/ConfirmForm';
import { MatchesPanel } from '../features/leadDetail/MatchesPanel';
import { RecordingsPanel } from '../features/leadDetail/RecordingsPanel';
import { SourceDataCard } from '../features/leadDetail/SourceDataCard';
import { useAddLeadModal } from '../features/modals/AddLeadModal';
import { ApiError } from '../lib/api';
import { useLead, useToggleHot } from '../lib/queries';

export default function LeadDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { push } = useToast();
  const { openAddLead, addLeadModal } = useAddLeadModal();
  const { data: lead, isLoading, error } = useLead(id);
  const toggleHot = useToggleHot(id ?? '');

  const onToggleHot = () => {
    if (!lead) return;
    const next = !lead.is_hot;
    toggleHot.mutate(next, {
      onSuccess: () =>
        push(
          next
            ? { kind: 'gold', title: 'Marked as immediate buyer', sub: `${lead.name} jumps the queue` }
            : { kind: 'blue', title: 'Immediate-buyer flag removed' },
        ),
    });
  };

  return (
    <>
      <Topbar title="Lead Details" onAddLead={openAddLead} />
      <div className="view">
        <button type="button" className="back-link" onClick={() => navigate(-1)}>
          ← Back
        </button>

        {isLoading && <div className="empty">Loading lead…</div>}
        {error && (
          <div className="note">
            {error instanceof ApiError ? error.detail : 'Could not load this lead.'}
          </div>
        )}

        {lead && (
          <>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                flexWrap: 'wrap',
                margin: '4px 0 18px',
              }}
            >
              <Avatar name={lead.name} size={42} />
              <span
                style={{
                  fontFamily: "'Bricolage Grotesque',sans-serif",
                  fontSize: 21,
                  fontWeight: 700,
                  lineHeight: 1.1,
                }}
              >
                {lead.name}
              </span>
              <button
                type="button"
                className="btn ghost sm"
                title={lead.is_hot ? 'Immediate buyer — click to unflag' : 'Flag as immediate buyer'}
                onClick={onToggleHot}
                disabled={toggleHot.isPending}
                style={
                  lead.is_hot
                    ? {
                        color: 'var(--accent)',
                        borderColor: 'var(--accent)',
                        background: 'var(--accent-soft)',
                        padding: '6px 8px',
                      }
                    : { color: 'var(--muted)', padding: '6px 8px' }
                }
              >
                <IconFlame size={15} />
              </button>
              <span className="mono" style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
                {lead.phone}
              </span>
              <SrcBadge source={lead.source} />
              <StageChip stage={lead.stage} />
              <TatChip tat={lead.tat} />
              <span style={{ marginLeft: 'auto', fontSize: 12.5, color: 'var(--ink-2)' }}>
                Assigned to{' '}
                <b style={{ fontWeight: 700 }}>{lead.assigned_to?.name ?? 'Unassigned'}</b>
              </span>
            </div>

            <div className="detail-grid">
              <div style={{ display: 'grid', gap: 16 }}>
                <SourceDataCard key={`src-${lead.id}`} lead={lead} />
                <ConfirmForm key={`confirm-${lead.id}`} lead={lead} />
                <ActivityTimeline activity={lead.activity} />
              </div>
              <div style={{ display: 'grid', gap: 16 }}>
                <MatchesPanel leadId={lead.id} kind="inventory" />
                <MatchesPanel leadId={lead.id} kind="supply" />
                <RecordingsPanel recordings={lead.recordings} />
              </div>
            </div>
          </>
        )}
      </div>
      {addLeadModal}
    </>
  );
}
