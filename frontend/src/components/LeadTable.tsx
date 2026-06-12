import type { LeadRow } from '../lib/types';
import { Avatar } from './Avatar';
import { EmptyState } from './EmptyState';
import { PlanChip } from './PlanChip';
import { SrcBadge, SOURCE_LABELS } from './SrcBadge';
import { StageChip } from './StageChip';
import { TatChip } from './TatChip';
import { WaButton } from './WaButton';

export interface LeadTableProps {
  leads: LeadRow[];
  /**
   * 'new'     — Lead (+source in brackets) · City · Society (source) · Config ·
   *             Budget · Plan to Buy · Assigned To · WhatsApp
   * 'segment' — Lead · Source · Stage · TAT · Society · Assigned · Visits action
   */
  variant: 'new' | 'segment';
  onRowClick: (lead: LeadRow) => void;
  /** 'segment' variant only — the "📅 Visits" row action. */
  onVisitClick?: (lead: LeadRow) => void;
}

function Who({ lead, withSource }: { lead: LeadRow; withSource?: boolean }) {
  return (
    <div className="who">
      <Avatar name={lead.name} size={32} />
      <div>
        <div className="w-name">
          {lead.name}
          {lead.is_hot && <span title="Immediate buyer"> 🔥</span>}
          {withSource && <span className="src-inline"> ({SOURCE_LABELS[lead.source]})</span>}
        </div>
        <div className="w-ph">{lead.phone}</div>
      </div>
    </div>
  );
}

/** The standard lead table (.lead-row hover, .who cells, chips). */
export function LeadTable({ leads, variant, onRowClick, onVisitClick }: LeadTableProps) {
  if (leads.length === 0) {
    return <EmptyState msg="No leads here yet" />;
  }

  if (variant === 'new') {
    return (
      <table>
        <thead>
          <tr>
            <th>Lead</th>
            <th>City</th>
            <th>Society (source)</th>
            <th>Config</th>
            <th>Budget</th>
            <th>Plan to Buy</th>
            <th>Assigned To</th>
            <th>WhatsApp</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((lead) => (
            <tr key={lead.id} className="lead-row" onClick={() => onRowClick(lead)}>
              <td>
                <Who lead={lead} withSource />
              </td>
              <td>{lead.city ?? '—'}</td>
              <td>{lead.society ?? '—'}</td>
              <td>{lead.configuration ? <span className="chip">{lead.configuration}</span> : '—'}</td>
              <td>{lead.budget_label ?? '—'}</td>
              <td>
                <PlanChip plan={lead.plan_to_buy} />
              </td>
              <td>{lead.assigned_to?.name ?? '—'}</td>
              <td>
                <WaButton phone={lead.phone} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Lead</th>
          <th>Source</th>
          <th>Stage</th>
          <th>TAT</th>
          <th>Society</th>
          <th>Assigned</th>
          <th>Visits</th>
        </tr>
      </thead>
      <tbody>
        {leads.map((lead) => (
          <tr key={lead.id} className="lead-row" onClick={() => onRowClick(lead)}>
            <td>
              <Who lead={lead} />
            </td>
            <td>
              <SrcBadge source={lead.source} />
            </td>
            <td>
              <StageChip stage={lead.stage} />
            </td>
            <td>
              <TatChip tat={lead.tat} />
            </td>
            <td>{lead.society ?? '—'}</td>
            <td>{lead.assigned_to?.name ?? '—'}</td>
            <td>
              <button
                type="button"
                className="btn ghost sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onVisitClick?.(lead);
                }}
              >
                📅 Visits
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
