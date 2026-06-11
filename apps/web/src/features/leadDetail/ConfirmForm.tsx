/**
 * "Lead data confirmed on call" — the Q1–Q6 confirm form
 * (POST /leads/:id/confirm). When the lead is already confirmed the answers
 * render read-only on top with a ✓ Qualified pill, and the pre-filled form
 * below allows a re-confirm (overwrites).
 *
 * Mandatory: Q1 purpose, Q2 budget, Q3 configuration, Q6 office-willing —
 * validated client-side and re-mapped from a 422 ApiError.fields envelope.
 */
import { useMemo, useState } from 'react';
import { MultiSelect } from '../../components/MultiSelect';
import { OfficePitch } from '../../components/OfficePitch';
import { IconQualified } from '../../components/icons';
import { useToast } from '../../components/Toast';
import { ApiError } from '../../lib/api';
import { formatDate, formatLacs } from '../../lib/format';
import { useConfirmLead, useLocalities, useSocieties } from '../../lib/queries';
import type { LeadDetail, OfficeWilling, Purpose } from '../../lib/types';

const CONFIGS = ['1 BHK', '2 BHK', '3 BHK', '3.5 BHK', '4 BHK'];
const PURPOSE_LABELS: Record<Purpose, string> = {
  self_use: 'Self use',
  investment: 'Investment',
};
const OFFICE_LABELS: Record<OfficeWilling, string> = { yes: 'Yes', no: 'No', maybe: 'Maybe' };
const OFFICE_OPTIONS: OfficeWilling[] = ['yes', 'no', 'maybe'];

function FieldError({ msg }: { msg?: string }) {
  if (!msg) return null;
  return (
    <div className="mand-flag" style={{ margin: '6px 0 0', padding: '6px 10px', fontSize: 11.5 }}>
      {msg}
    </div>
  );
}

export function ConfirmForm({ lead }: { lead: LeadDetail }) {
  const confirmLead = useConfirmLead(lead.id);
  const { push } = useToast();
  const societiesQ = useSocieties();
  const localitiesQ = useLocalities();

  const cd = lead.confirmed_data;

  /* form state — pre-filled from confirmed data when present */
  const [purpose, setPurpose] = useState<'' | Purpose>(cd?.purpose ?? '');
  const [budget, setBudget] = useState(
    cd?.budget_value_lacs !== null && cd?.budget_value_lacs !== undefined
      ? String(cd.budget_value_lacs)
      : '',
  );
  const [configuration, setConfiguration] = useState(cd?.configuration ?? '');
  const [shortlist, setShortlist] = useState<string[]>(lead.shortlist_societies);
  const [localities, setLocalities] = useState<string[]>(lead.preferred_localities);
  const [office, setOffice] = useState<'' | OfficeWilling>(cd?.office_willing ?? '');
  const [prefDate, setPrefDate] = useState(
    cd?.office_preferred_date ? cd.office_preferred_date.slice(0, 10) : '',
  );
  const [remark, setRemark] = useState(cd?.remark ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState<string | null>(null);

  const societyOptions = useMemo(() => {
    const fromApi = (societiesQ.data ?? [])
      .filter((s) => !lead.city || s.city === lead.city)
      .map((s) => s.name);
    return Array.from(new Set([...fromApi, ...shortlist]));
  }, [societiesQ.data, lead.city, shortlist]);

  const localityOptions = useMemo(() => {
    const fromApi = (localitiesQ.data ?? [])
      .filter((l) => !lead.city || l.city === lead.city)
      .map((l) => l.name);
    return Array.from(new Set([...fromApi, ...localities]));
  }, [localitiesQ.data, lead.city, localities]);

  const budgetNum = Number(budget);
  const budgetPreview = budget.trim() !== '' && !isNaN(budgetNum) && budgetNum > 0;

  const submit = async () => {
    const errs: Record<string, string> = {};
    if (!purpose) errs.purpose = 'Q1 — purpose is mandatory';
    if (!budgetPreview) errs.budget_value_lacs = 'Q2 — enter the confirmed budget in lacs';
    if (!configuration) errs.configuration = 'Q3 — configuration is mandatory';
    if (!office) errs.office_willing = 'Q6 — office-visit answer is mandatory';
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      setSummary('Mandatory fields missing — answer Q1, Q2, Q3 and Q6 to qualify this lead.');
      return;
    }
    setErrors({});
    setSummary(null);
    try {
      await confirmLead.mutateAsync({
        purpose: purpose as Purpose,
        budget_value_lacs: budgetNum,
        configuration,
        shortlist_societies: shortlist,
        preferred_localities: localities,
        office_willing: office as OfficeWilling,
        office_preferred_date: office !== 'no' && prefDate ? prefDate : null,
        remark: remark.trim() || null,
      });
      push({ kind: 'green', title: 'Lead qualified', sub: 'Moved to Qualified · TAT cleared' });
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 422 && e.fields) setErrors(e.fields);
        setSummary(e.detail);
      } else {
        setSummary('Something went wrong — try again.');
      }
    }
  };

  return (
    <div className="card panel-pad">
      <div className="panel-title">
        <IconQualified size={16} />
        <span>Lead data confirmed on call</span>
        {lead.confirmed && (
          <span
            style={{
              marginLeft: 'auto',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              padding: '3px 10px',
              borderRadius: 20,
              fontSize: 11.5,
              fontWeight: 600,
              background: 'var(--emerald-soft)',
              color: 'var(--emerald)',
            }}
          >
            ✓ Qualified
          </span>
        )}
      </div>

      {lead.confirmed && cd && (
        <div
          style={{
            border: '1px solid var(--line)',
            borderRadius: 11,
            padding: 12,
            marginBottom: 14,
            background: '#fbfbfa',
          }}
        >
          <div className="opt-dl" style={{ marginBottom: 0 }}>
            <div>
              <div className="k">Purpose</div>
              <div className="v">{cd.purpose ? PURPOSE_LABELS[cd.purpose] : '—'}</div>
            </div>
            <div>
              <div className="k">Budget</div>
              <div className="v">{formatLacs(cd.budget_value_lacs)}</div>
            </div>
            <div>
              <div className="k">Configuration</div>
              <div className="v">{cd.configuration ?? '—'}</div>
            </div>
            <div>
              <div className="k">Office visit</div>
              <div className="v">
                {cd.office_willing ? OFFICE_LABELS[cd.office_willing] : '—'}
                {cd.office_preferred_date ? ` · ${formatDate(cd.office_preferred_date)}` : ''}
              </div>
            </div>
            {cd.remark && (
              <div>
                <div className="k">Remark</div>
                <div className="v">{cd.remark}</div>
              </div>
            )}
            <div>
              <div className="k">Confirmed</div>
              <div className="v mono">{formatDate(cd.confirmed_at)}</div>
            </div>
          </div>
          {(lead.shortlist_societies.length > 0 || lead.preferred_localities.length > 0) && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
              {lead.shortlist_societies.map((s) => (
                <span key={`s-${s}`} className="chip">
                  {s}
                </span>
              ))}
              {lead.preferred_localities.map((l) => (
                <span
                  key={`l-${l}`}
                  className="chip"
                  style={{ background: 'var(--blue-soft)', color: 'var(--blue)' }}
                >
                  {l}
                </span>
              ))}
            </div>
          )}
          <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 10 }}>
            Re-confirming below overwrites these answers (follow-up call updates).
          </div>
        </div>
      )}

      {summary && <div className="mand-flag">{summary}</div>}

      <div className="two">
        <div className="field">
          <label>
            Q1 · Purpose <span className="req">*</span>
          </label>
          <select
            className={errors.purpose ? 'invalid' : undefined}
            value={purpose}
            onChange={(e) => setPurpose(e.target.value as '' | Purpose)}
          >
            <option value="">Select…</option>
            <option value="self_use">Self use</option>
            <option value="investment">Investment</option>
          </select>
          <FieldError msg={errors.purpose} />
        </div>
        <div className="field">
          <label>
            Q2 · ₹ budget (lacs) <span className="req">*</span>
          </label>
          <input
            type="number"
            min={1}
            placeholder="e.g. 85"
            className={errors.budget_value_lacs ? 'invalid' : undefined}
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
          />
          {budgetPreview && (
            <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 4 }}>
              = {formatLacs(budgetNum)}
            </div>
          )}
          <FieldError msg={errors.budget_value_lacs} />
        </div>
      </div>

      <div className="field">
        <label>
          Q3 · Configuration <span className="req">*</span>
        </label>
        <select
          className={errors.configuration ? 'invalid' : undefined}
          value={configuration}
          onChange={(e) => setConfiguration(e.target.value)}
        >
          <option value="">Select…</option>
          {(configuration && !CONFIGS.includes(configuration)
            ? [configuration, ...CONFIGS]
            : CONFIGS
          ).map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <FieldError msg={errors.configuration} />
      </div>

      <div className="field">
        <label>Q4 · Shortlisted societies</label>
        <MultiSelect
          options={societyOptions}
          value={shortlist}
          onChange={setShortlist}
          placeholder={
            societiesQ.isLoading ? 'Loading societies…' : 'Select shortlisted societies…'
          }
          invalid={!!errors.shortlist_societies}
        />
        <FieldError msg={errors.shortlist_societies} />
      </div>

      <div className="field">
        <label>Q5 · Preferred localities</label>
        <MultiSelect
          options={localityOptions}
          value={localities}
          onChange={setLocalities}
          placeholder={
            localitiesQ.isLoading ? 'Loading localities…' : 'Select preferred localities…'
          }
          invalid={!!errors.preferred_localities}
        />
        <FieldError msg={errors.preferred_localities} />
      </div>

      <div className="field">
        <label>
          Q6 · Open to an office visit? <span className="req">*</span>
        </label>
        <div style={{ display: 'flex', gap: 8 }}>
          {OFFICE_OPTIONS.map((o) => (
            <button
              key={o}
              type="button"
              className={`btn sm ${office === o ? 'green' : 'ghost'}`}
              onClick={() => setOffice(o)}
            >
              {OFFICE_LABELS[o]}
            </button>
          ))}
        </div>
        <FieldError msg={errors.office_willing} />
      </div>

      {(office === 'yes' || office === 'maybe') && (
        <div className="field">
          <label>Preferred date</label>
          <input
            type="date"
            className={errors.office_preferred_date ? 'invalid' : undefined}
            value={prefDate}
            onChange={(e) => setPrefDate(e.target.value)}
          />
          <FieldError msg={errors.office_preferred_date} />
        </div>
      )}

      {(office === 'no' || office === 'maybe') && <OfficePitch city={lead.city ?? 'your city'} />}

      <div className="field">
        <label>Remark (optional)</label>
        <textarea
          placeholder="Anything else from the call…"
          value={remark}
          onChange={(e) => setRemark(e.target.value)}
        />
      </div>

      <button
        type="button"
        className="btn green"
        style={{ width: '100%', justifyContent: 'center' }}
        onClick={submit}
        disabled={confirmLead.isPending}
      >
        {confirmLead.isPending ? 'Confirming…' : '✓ Confirm & qualify lead'}
      </button>
    </div>
  );
}
