/**
 * "Lead data captured from {source}" card — the source-layer of the two-layer
 * data model. Read-only key/value grid for everyone; Admin gets an inline
 * editor (PATCH /leads/:id/source-data). Other roles see a lock tag.
 */
import { useState } from 'react';
import { IconLeads } from '../../components/icons';
import { PlanChip, PLAN_META } from '../../components/PlanChip';
import { SOURCE_LABELS } from '../../components/SrcBadge';
import { useToast } from '../../components/Toast';
import { ApiError } from '../../lib/api';
import { budgetLabel } from '../../lib/format';
import { usePatchSourceData } from '../../lib/queries';
import type { LeadDetail, PlanToBuy, SourceData } from '../../lib/types';
import { useAuth } from '../../store/auth';

const CITIES = ['Gurgaon', 'Noida', 'Ghaziabad'];
const CONFIGS = ['1 BHK', '2 BHK', '3 BHK', '3.5 BHK', '4 BHK'];
const PLANS = Object.keys(PLAN_META) as PlanToBuy[];

interface EditState {
  city: string;
  society: string;
  configuration: string;
  budgetMin: string;
  budgetMax: string;
  plan: '' | PlanToBuy;
}

function withCurrent(options: string[], current: string | null): string[] {
  if (current && !options.includes(current)) return [current, ...options];
  return options;
}

export function SourceDataCard({ lead }: { lead: LeadDetail }) {
  const { user } = useAuth();
  const { push } = useToast();
  const patch = usePatchSourceData(lead.id);

  const isAdmin = user?.role === 'admin';
  const sd = lead.source_data;

  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [form, setForm] = useState<EditState>({
    city: '',
    society: '',
    configuration: '',
    budgetMin: '',
    budgetMax: '',
    plan: '',
  });

  const startEdit = () => {
    setForm({
      city: sd.city ?? '',
      society: sd.society ?? '',
      configuration: sd.configuration ?? '',
      budgetMin: sd.budget_min_lacs !== null ? String(sd.budget_min_lacs) : '',
      budgetMax: sd.budget_max_lacs !== null ? String(sd.budget_max_lacs) : '',
      plan: sd.plan_to_buy ?? '',
    });
    setErr(null);
    setEditing(true);
  };

  const set = <K extends keyof EditState>(key: K, value: EditState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = async () => {
    setErr(null);
    const payload: Partial<SourceData> = {
      city: form.city || null,
      society: form.society.trim() || null,
      configuration: form.configuration || null,
      budget_min_lacs: form.budgetMin.trim() === '' ? null : Number(form.budgetMin),
      budget_max_lacs: form.budgetMax.trim() === '' ? null : Number(form.budgetMax),
      plan_to_buy: form.plan || null,
    };
    try {
      await patch.mutateAsync(payload);
      push({ kind: 'green', title: 'Source data updated', sub: 'Matches will refresh' });
      setEditing(false);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : 'Could not save — try again.');
    }
  };

  const budgetDisplay = sd.budget_band ?? budgetLabel(sd.budget_min_lacs, sd.budget_max_lacs);

  return (
    <div className="card panel-pad">
      <div className="panel-title">
        <IconLeads size={16} />
        <span>Lead data captured from {SOURCE_LABELS[lead.source]}</span>
        <span style={{ marginLeft: 'auto' }}>
          {isAdmin ? (
            !editing && (
              <button type="button" className="btn ghost sm" onClick={startEdit}>
                Edit
              </button>
            )
          ) : (
            <span
              className="mono"
              style={{
                fontSize: 10.5,
                fontWeight: 500,
                color: 'var(--muted)',
                textTransform: 'uppercase',
                letterSpacing: '.06em',
              }}
            >
              🔒 Locked — Admin only
            </span>
          )}
        </span>
      </div>

      {!editing && (
        <div className="opt-dl" style={{ marginBottom: 0 }}>
          <div>
            <div className="k">Budget</div>
            <div className="v">{budgetDisplay}</div>
          </div>
          <div>
            <div className="k">City</div>
            <div className="v">{sd.city ?? '—'}</div>
          </div>
          <div>
            <div className="k">Society</div>
            <div className="v">{sd.society ?? '—'}</div>
          </div>
          <div>
            <div className="k">Configuration</div>
            <div className="v">{sd.configuration ?? '—'}</div>
          </div>
          <div>
            <div className="k">Plan to Buy</div>
            <div className="v">
              <PlanChip plan={sd.plan_to_buy} />
            </div>
          </div>
        </div>
      )}

      {editing && (
        <div>
          <div className="two">
            <div className="field">
              <label>City</label>
              <select value={form.city} onChange={(e) => set('city', e.target.value)}>
                <option value="">—</option>
                {withCurrent(CITIES, sd.city).map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Society</label>
              <input
                type="text"
                value={form.society}
                placeholder="e.g. DLF The Crest"
                onChange={(e) => set('society', e.target.value)}
              />
            </div>
          </div>
          <div className="two">
            <div className="field">
              <label>Configuration</label>
              <select
                value={form.configuration}
                onChange={(e) => set('configuration', e.target.value)}
              >
                <option value="">—</option>
                {withCurrent(CONFIGS, sd.configuration).map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Plan to Buy</label>
              <select
                value={form.plan}
                onChange={(e) => set('plan', e.target.value as '' | PlanToBuy)}
              >
                <option value="">—</option>
                {PLANS.map((p) => (
                  <option key={p} value={p}>
                    {PLAN_META[p].label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="two">
            <div className="field">
              <label>Budget min (lacs)</label>
              <input
                type="number"
                min={0}
                value={form.budgetMin}
                placeholder="e.g. 70"
                onChange={(e) => set('budgetMin', e.target.value)}
              />
            </div>
            <div className="field">
              <label>Budget max (lacs)</label>
              <input
                type="number"
                min={0}
                value={form.budgetMax}
                placeholder="e.g. 90"
                onChange={(e) => set('budgetMax', e.target.value)}
              />
            </div>
          </div>
          {err && <div className="mand-flag">{err}</div>}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => setEditing(false)}
              disabled={patch.isPending}
            >
              Cancel
            </button>
            <button type="button" className="btn green sm" onClick={save} disabled={patch.isPending}>
              {patch.isPending ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
