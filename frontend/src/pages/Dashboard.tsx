import { useNavigate } from 'react-router-dom';
import { KpiCard } from '../components/KpiCard';
import { Topbar } from '../components/Topbar';
import {
  IconBell,
  IconConverted,
  IconFlame,
  IconLeads,
  IconPipeline,
  IconQualified,
} from '../components/icons';
import { useAddLeadModal } from '../features/modals/AddLeadModal';
import { ApiError } from '../lib/api';
import { useMetrics } from '../lib/queries';

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: metrics, isLoading, error } = useMetrics();
  const { openAddLead, addLeadModal } = useAddLeadModal();

  return (
    <>
      <Topbar onAddLead={openAddLead} />
      <div className="view">
        {isLoading && <div className="empty">Loading…</div>}
        {error != null && (
          <div className="note">
            {error instanceof ApiError ? error.detail : 'Failed to load metrics.'}
          </div>
        )}
        {metrics && (
          <div className="kpi-row">
            <KpiCard
              label="New"
              value={metrics.new}
              accent="var(--blue)"
              soft="var(--blue-soft)"
              icon={<IconLeads size={16} />}
              onClick={() => navigate('/leads/new')}
            />
            <KpiCard
              label="Qualified"
              value={metrics.qualified}
              accent="var(--cyan)"
              soft="var(--cyan-soft)"
              icon={<IconQualified size={16} />}
              onClick={() => navigate('/leads/qualified')}
            />
            <KpiCard
              label="Immediate Buyers"
              value={metrics.immediate}
              accent="var(--coral)"
              soft="var(--coral-soft)"
              icon={<IconFlame size={16} />}
              onClick={() => navigate('/leads/qualified')}
            />
            <KpiCard
              label="Follow-ups due Today"
              value={metrics.followups_due_today}
              accent="var(--amber)"
              soft="var(--amber-soft)"
              icon={<IconBell size={16} />}
              onClick={() => navigate('/reminders')}
            />
            <KpiCard
              label="Pipeline"
              value={metrics.pipeline}
              accent="var(--indigo)"
              soft="var(--indigo-soft)"
              icon={<IconPipeline size={16} />}
              onClick={() => navigate('/leads/pipeline')}
            />
            <KpiCard
              label="Converted"
              value={metrics.converted}
              accent="var(--emerald)"
              soft="var(--emerald-soft)"
              icon={<IconConverted size={16} />}
              onClick={() => navigate('/leads/converted')}
            />
          </div>
        )}
      </div>
      {addLeadModal}
    </>
  );
}
