/**
 * Add society insight modal — POST /v1/societies/insights.
 * Society options come from useSocieties(); city derives from the chosen society.
 */
import { useEffect, useMemo, useState } from 'react';
import { Modal } from '../../components/Modal';
import { useToast } from '../../components/Toast';
import { useAddInsight, useSocieties } from '../../lib/queries';
import { ApiError } from '../../lib/api';

const CITIES = ['Gurgaon', 'Noida', 'Ghaziabad'];

export interface AddInsightModalProps {
  open: boolean;
  onClose: () => void;
  defaultSociety?: string;
  defaultCity?: string;
}

export function AddInsightModal({ open, onClose, defaultSociety, defaultCity }: AddInsightModalProps) {
  const [society, setSociety] = useState('');
  const [city, setCity] = useState('Gurgaon');
  const [note, setNote] = useState('');
  const [tried, setTried] = useState(false);
  const { push } = useToast();
  const societies = useSocieties();
  const addInsight = useAddInsight();

  // Re-seed the form from defaults each time the modal opens.
  useEffect(() => {
    if (!open) return;
    setSociety(defaultSociety ?? '');
    setCity(defaultCity ?? 'Gurgaon');
    setNote('');
    setTried(false);
    addInsight.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, defaultSociety, defaultCity]);

  const societyOptions = useMemo(() => {
    const list = societies.data ?? [];
    const names = list.map((s) => s.name);
    if (defaultSociety && !names.includes(defaultSociety)) names.unshift(defaultSociety);
    return names;
  }, [societies.data, defaultSociety]);

  const cityOptions = useMemo(
    () => (city && !CITIES.includes(city) ? [...CITIES, city] : CITIES),
    [city],
  );

  const onSocietyChange = (name: string) => {
    setSociety(name);
    const match = societies.data?.find((s) => s.name === name);
    if (match?.city) setCity(match.city);
  };

  const noteInvalid = !note.trim();
  const societyInvalid = !society;

  const submit = async () => {
    setTried(true);
    if (noteInvalid || societyInvalid) return;
    try {
      await addInsight.mutateAsync({ society, city, note: note.trim() });
      push({ kind: 'gold', title: 'Insight added' });
      onClose();
    } catch {
      // ApiError surfaced below via addInsight.error
    }
  };

  const apiError = addInsight.error
    ? addInsight.error instanceof ApiError
      ? addInsight.error.detail
      : addInsight.error.message
    : null;

  return (
    <Modal
      title="Add society insight"
      open={open}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn gold"
            onClick={submit}
            disabled={addInsight.isPending}
          >
            {addInsight.isPending ? 'Adding…' : 'Add Insight'}
          </button>
        </>
      }
    >
      <div className="two">
        <div className="field">
          <label>
            Society <span className="req">*</span>
          </label>
          <select
            className={tried && societyInvalid ? 'invalid' : undefined}
            value={society}
            onChange={(e) => onSocietyChange(e.target.value)}
          >
            <option value="">
              {societies.isLoading ? 'Loading societies…' : 'Select society…'}
            </option>
            {societyOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>City</label>
          <select value={city} onChange={(e) => setCity(e.target.value)}>
            {cityOptions.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="field">
        <label>
          Insight <span className="req">*</span>
        </label>
        <textarea
          className={tried && noteInvalid ? 'invalid' : undefined}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Buyers ask about RERA status / possession timeline…"
          rows={4}
        />
      </div>

      {tried && (noteInvalid || societyInvalid) && (
        <div className="mand-flag">⚠ Pick a society and write the insight before saving.</div>
      )}
      {apiError && <div className="note">{apiError}</div>}
    </Modal>
  );
}
