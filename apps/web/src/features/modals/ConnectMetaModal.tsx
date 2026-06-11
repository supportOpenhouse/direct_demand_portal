/**
 * Connect Meta Lead Ads modal — demo-only integration stub (per prototype).
 * Fields are not wired anywhere; "Connect" just fires a toast and closes.
 */
import { Modal } from '../../components/Modal';
import { useToast } from '../../components/Toast';
import { MetaLogo } from '../../components/icons';

export function ConnectMetaModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { push } = useToast();

  const connect = () => {
    push({ kind: 'blue', title: 'Meta Lead Ads connected', sub: 'Test lead will arrive via webhook' });
    onClose();
  };

  return (
    <Modal
      title="Connect Meta Lead Ads"
      open={open}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn primary" onClick={connect}>
            Connect
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 16 }}>
        <span style={{ color: '#1877f2', flexShrink: 0, marginTop: 2 }}>
          <MetaLogo size={30} />
        </span>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55 }}>
          Connect your Meta Lead Ads form and every submission lands here instantly — auto-assigned
          to an RM with the TAT timer running and a WhatsApp alert fired. No CSV exports, no manual
          entry.
        </p>
      </div>

      <div className="field">
        <label>Page ID</label>
        <input placeholder="e.g. 104857293847562" />
      </div>
      <div className="field">
        <label>Form ID</label>
        <input placeholder="e.g. 89234710384756" />
      </div>
      <div className="field">
        <label>Access token</label>
        <input placeholder="EAAB…" />
      </div>

      <div className="note">
        Demo integration — these fields aren't saved. In production this completes the Meta OAuth
        flow and subscribes the leadgen webhook.
      </div>
    </Modal>
  );
}
