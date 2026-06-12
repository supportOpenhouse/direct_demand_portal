/**
 * New Leads — leads captured from sources, awaiting the confirmation call.
 * One full-width card with the 'new' variant lead table and a cyan shortcut
 * to the Qualified Leads segment.
 */
import { useNavigate } from 'react-router-dom';
import { LeadTable } from '../components/LeadTable';
import { Topbar } from '../components/Topbar';
import { useAddLeadModal } from '../features/modals/AddLeadModal';
import { ApiError } from '../lib/api';
import { useLeads } from '../lib/queries';

export default function NewLeads() {
  const navigate = useNavigate();
  const { openAddLead, addLeadModal } = useAddLeadModal();
  const { data, error } = useLeads('new');

  return (
    <>
      <Topbar onAddLead={openAddLead} />
      <div className="view">
        <div className="page-sub">
          Leads captured from sources — confirm on call within the TAT window.
        </div>
        <div className="card panel-pad">
          <div className="section-head">
            <div className="panel-title">New Leads: Urgent action required</div>
            <button
              type="button"
              className="btn sm"
              style={{ background: 'var(--cyan-soft)', color: 'var(--cyan)' }}
              onClick={() => navigate('/leads/qualified')}
            >
              Qualified Leads →
            </button>
          </div>
          {error ? (
            <div className="note">
              {error instanceof ApiError ? error.detail : 'Could not load leads.'}
            </div>
          ) : (
            <LeadTable
              variant="new"
              leads={data?.items ?? []}
              onRowClick={(l) => navigate('/leads/' + l.id)}
            />
          )}
        </div>
      </div>
      {addLeadModal}
    </>
  );
}
