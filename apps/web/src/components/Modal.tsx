import { useEffect, type ReactNode } from 'react';

export interface ModalProps {
  title: string;
  open: boolean;
  onClose: () => void;
  footer?: ReactNode;
  /** .modal.wide (940px) — visit planner etc. */
  wide?: boolean;
  children: ReactNode;
}

/** Blurred overlay + slide-up modal (.overlay/.modal/.mh/.mb/.mf). */
export function Modal({ title, open, onClose, footer, wide, children }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={`modal${wide ? ' wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="mh">
          <h3>{title}</h3>
          <button type="button" className="x" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="mb">{children}</div>
        {footer && <div className="mf">{footer}</div>}
      </div>
    </div>
  );
}
