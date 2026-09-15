/* Prototype toast system (#toasts / .toast) as a React context. */
import { createContext, useCallback, useContext, useRef, useState, ReactNode } from "react";
import {
  IconCheck,
  IconInfo,
  IconWarn,
} from "./icons";
import { WhatsAppIcon } from "./icons";

type Kind = "green" | "wa" | "gold" | "blue";
interface ToastItem {
  id: number;
  msg: string;
  kind: Kind;
  icon: ReactNode;
  leaving?: boolean;
}

/* The icon is derived from the kind. Callers used to pass a glyph on every call
   ("⚠", "✓") — restating what the kind already said, in 40 places. */
const KIND_ICON: Record<Kind, ReactNode> = {
  green: <IconCheck />, gold: <IconWarn />, blue: <IconInfo />, wa: <WhatsAppIcon />,
};

const ToastCtx = createContext<(msg: string, kind?: Kind, icon?: ReactNode) => void>(() => {});

export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const push = useCallback((msg: string, kind: Kind = "green", icon?: ReactNode) => {
    const id = ++seq.current;
    setToasts((t) => [...t, { id, msg, kind, icon: icon ?? KIND_ICON[kind] }]);
    setTimeout(() => setToasts((t) => t.map((x) => (x.id === id ? { ...x, leaving: true } : x))), 3400);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3700);
  }, []);

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div id="toasts">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast ${t.kind}`}
            style={t.leaving ? { transition: ".3s", opacity: 0, transform: "translateX(40px)" } : undefined}
          >
            <div className="ic" style={{ color: "var(--on-accent)", fontSize: 14, display: "grid", placeItems: "center" }}>
              {t.icon}
            </div>
            <div>{t.msg}</div>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
