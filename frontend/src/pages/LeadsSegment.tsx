/**
 * Qualified / Pipeline / Converted leads — one card with the standard
 * 'segment' lead table. The segment is derived from the current pathname
 * (/leads/qualified|pipeline|converted); the router-passed prop is a fallback.
 * The 📅 Visits row action opens the Visit Planner modal.
 */
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { LeadTable } from '../components/LeadTable';
import { Topbar } from '../components/Topbar';
import { useAddLeadModal } from '../features/modals/AddLeadModal';
import { VisitPlannerModal } from '../features/visitPlanner/VisitPlannerModal';
import { ApiError } from '../lib/api';
import { useLeads } from '../lib/queries';
import type { LeadRow } from '../lib/types';

const SEGMENTS = ['qualified', 'pipeline', 'converted'] as const;
type SegmentKey = (typeof SEGMENTS)[number];

const SUBS: Record<SegmentKey, string> = {
  qualified: 'Confirmed on call, active, < 7 days since qualification.',
  pipeline: 'Auto-aged: ≥ 7 days since qualification — keep working them.',
  converted: 'Won deals.',
};

export default function LeadsSegment({ segment }: { segment?: SegmentKey }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { openAddLead, addLeadModal } = useAddLeadModal();
  const [plannerLead, setPlannerLead] = useState<LeadRow | null>(null);

  const seg: SegmentKey =
    SEGMENTS.find((s) => pathname.startsWith('/leads/' + s)) ?? segment ?? 'qualified';

  const { data, error } = useLeads(seg);

  return (
    <>
      <Topbar onAddLead={openAddLead} />
      <div className="view">
        <div className="page-sub">{SUBS[seg]}</div>
        <div className="card panel-pad">
          {error ? (
            <div className="note">
              {error instanceof ApiError ? error.detail : 'Could not load leads.'}
            </div>
          ) : (
            <LeadTable
              variant="segment"
              leads={data?.items ?? []}
              onRowClick={(l) => navigate('/leads/' + l.id)}
              onVisitClick={(l) => setPlannerLead(l)}
            />
          )}
        </div>
      </div>
      <VisitPlannerModal lead={plannerLead} onClose={() => setPlannerLead(null)} />
      {addLeadModal}
    </>
  );
}
