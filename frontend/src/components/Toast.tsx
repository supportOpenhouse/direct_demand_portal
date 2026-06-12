/**
 * Toast system — bottom-right dark pills with a coloured icon square.
 * Wrap the app in <ToastProvider>; fire with
 *   const { push } = useToast();
 *   push({ kind: 'green', title: 'Lead qualified', sub: 'Moved to Qualified' });
 * Kinds: 'wa' | 'green' | 'gold' | 'blue'. Auto-dismisses after ~3.4s.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { WhatsAppLogo } from './icons';

export type ToastKind = 'wa' | 'green' | 'gold' | 'blue';

export interface ToastInput {
  kind: ToastKind;
  title: string;
  sub?: string;
}

interface ToastItem extends ToastInput {
  id: number;
}

export interface ToastContextValue {
  push: (toast: ToastInput) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const KIND_GLYPH: Record<ToastKind, ReactNode> = {
  wa: <WhatsAppLogo size={14} />,
  green: '✓',
  gold: '★',
  blue: 'ℹ',
};

const AUTO_DISMISS_MS = 3400;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const push = useCallback((toast: ToastInput) => {
    const id = ++seq.current;
    setItems((prev) => [...prev, { ...toast, id }]);
    setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, AUTO_DISMISS_MS);
  }, []);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div id="toasts">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <span className="tic">{KIND_GLYPH[t.kind]}</span>
            <div>
              <div className="t-title">{t.title}</div>
              {t.sub && <div className="t-sub">{t.sub}</div>}
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within <ToastProvider>');
  return ctx;
}
