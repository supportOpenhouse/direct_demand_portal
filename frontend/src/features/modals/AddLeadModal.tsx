/**
 * Add New Lead modal — manual ingestion via POST /v1/leads/ingest.
 * Demonstrates ingestion, round-robin assignment, TAT timer and WhatsApp alerts.
 *
 * Exports:
 *   AddLeadModal({open, onClose})
 *   useAddLeadModal(): {openAddLead, addLeadModal} — hook owns the open state.
 */
import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { Modal } from '../../components/Modal';
import { useToast } from '../../components/Toast';
import { SOURCE_LABELS } from '../../components/SrcBadge';
import { PLAN_META } from '../../components/PlanChip';
import { useIngestLead } from '../../lib/queries';
import { ApiError } from '../../lib/api';
import type { IngestPayload, PlanToBuy, Source } from '../../lib/types';

const SOURCES: Source[] = ['meta', 'gads', '99acres', 'magicbricks', 'youtube', 'whatsapp'];
const CITIES = ['Gurgaon', 'Noida', 'Ghaziabad'];
const CONFIGS = ['1 BHK', '2 BHK', '3 BHK', '3.5 BHK', '4 BHK'];
const PLANS = Object.keys(PLAN_META) as PlanToBuy[];

interface FormState {
  name: string;
  phone: string;
  source: '' | Source;
  city: string;
  society: string;
  configuration: string;
  budgetMin: string;
  budgetMax: string;
  plan: '' | PlanToBuy;
}

const BLANK: FormState = {
  name: '',
  phone: '',
  source: '',
  city: '',
  society: '',
  configuration: '',
  budgetMin: '',
  budgetMax: '',
  plan: '',
};

export function AddLeadModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form, setForm] = useState<FormState>(BLANK);
  const [tried, setTried] = useState(false);
  const { push } = useToast();
  const ingest = useIngestLead();

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const nameInvalid = !form.name.trim();
  const phoneInvalid = !/^\d{10}$/.test(form.phone.trim());
  const sourceInvalid = !form.source;
  const hasErrors = nameInvalid || phoneInvalid || sourceInvalid;

  const reset = useCallback(() => {
    setForm(BLANK);
    setTried(false);
    ingest.reset();
  }, [ingest]);

  const handleClose = () => {
    reset();
    onClose();
  };

  const submit = async () => {
    setTried(true);
    if (hasErrors) return;

    const min = form.budgetMin.trim() === '' ? null : Number(form.budgetMin);
    const max = form.budgetMax.trim() === '' ? null : Number(form.budgetMax);
    const payload: IngestPayload = {
      name: form.name.trim(),
      phone: form.phone.trim(),
      source: form.source as Source,
      city: form.city || null,
      society: form.society.trim() || null,
      configuration: form.configuration || null,
      budget_band: min != null && max != null ? `₹${min}L – ₹${max}L` : null,
      budget_min_lacs: min,
      budget_max_lacs: max,
      plan_to_buy: form.plan || null,
    };

    try {
      await ingest.mutateAsync(payload);
      push({ kind: 'green', title: 'Lead added', sub: 'Assigned + TAT timer started' });
      push({ kind: 'wa', title: 'WhatsApp alert sent to RM' });
      reset();
      onClose();
    } catch {
      // ApiError surfaced below via ingest.error
    }
  };

  const apiError = ingest.error
    ? ingest.error instanceof ApiError
      ? ingest.error.detail
      : ingest.error.message
    : null;

  return (
    <Modal
      title="Add New Lead"
      open={open}
      onClose={handleClose}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={handleClose}>
            Cancel
          </button>
          <button type="button" className="btn green" onClick={submit} disabled={ingest.isPending}>
            {ingest.isPending ? 'Adding…' : 'Add Lead'}
          </button>
        </>
      }
    >
      <div className="two">
        <div className="field">
          <label>
            Name <span className="req">*</span>
          </label>
          <input
            className={tried && nameInvalid ? 'invalid' : undefined}
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="Buyer's full name"
          />
        </div>
        <div className="field">
          <label>
            Phone <span className="req">*</span>
          </label>
          <input
            className={tried && phoneInvalid ? 'invalid' : undefined}
            value={form.phone}
            onChange={(e) => set('phone', e.target.value.replace(/\D/g, '').slice(0, 10))}
            placeholder="10-digit mobile"
            inputMode="numeric"
          />
        </div>
      </div>

      <div className="two">
        <div className="field">
          <label>
            Source <span className="req">*</span>
          </label>
          <select
            className={tried && sourceInvalid ? 'invalid' : undefined}
            value={form.source}
            onChange={(e) => set('source', e.target.value as '' | Source)}
          >
            <option value="">Select source…</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {SOURCE_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>City</label>
          <select value={form.city} onChange={(e) => set('city', e.target.value)}>
            <option value="">Select city…</option>
            {CITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="two">
        <div className="field">
          <label>Society</label>
          <input
            value={form.society}
            onChange={(e) => set('society', e.target.value)}
            placeholder="e.g. DLF Park Place"
          />
        </div>
        <div className="field">
          <label>Configuration</label>
          <select value={form.configuration} onChange={(e) => set('configuration', e.target.value)}>
            <option value="">Select…</option>
            {CONFIGS.map((c) => (
              <option key={c} value={c}>
                {c}
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
            onChange={(e) => set('budgetMin', e.target.value)}
            placeholder="e.g. 70"
          />
        </div>
        <div className="field">
          <label>Budget max (lacs)</label>
          <input
            type="number"
            min={0}
            value={form.budgetMax}
            onChange={(e) => set('budgetMax', e.target.value)}
            placeholder="e.g. 90"
          />
        </div>
      </div>

      <div className="field">
        <label>Plan to Buy</label>
        <select
          value={form.plan}
          onChange={(e) => set('plan', e.target.value as '' | PlanToBuy)}
        >
          <option value="">Select…</option>
          {PLANS.map((p) => (
            <option key={p} value={p}>
              {PLAN_META[p].label}
            </option>
          ))}
        </select>
      </div>

      {tried && hasErrors && (
        <div className="mand-flag">
          ⚠ Name, a valid 10-digit phone and source are mandatory.
        </div>
      )}
      {apiError && <div className="note">{apiError}</div>}
    </Modal>
  );
}

/** Owns the open state and renders the modal — wire openAddLead to Topbar's onAddLead. */
export function useAddLeadModal(): { openAddLead: () => void; addLeadModal: ReactNode } {
  const [open, setOpen] = useState(false);
  const openAddLead = useCallback(() => setOpen(true), []);
  const close = useCallback(() => setOpen(false), []);
  const addLeadModal = useMemo(() => <AddLeadModal open={open} onClose={close} />, [open, close]);
  return { openAddLead, addLeadModal };
}
