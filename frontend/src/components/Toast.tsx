/* Prototype toast system (#toasts / .toast) as a React context. */
import { createContext, useCallback, useContext, useRef, useState, ReactNode } from "react";

type Kind = "green" | "wa" | "gold" | "blue";
interface ToastItem {
  id: number;
  msg: string;
  kind: Kind;
  icon: string;
  leaving?: boolean;
}

const ToastCtx = createContext<(msg: string, kind?: Kind, icon?: string) => void>(() => {});

export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const push = useCallback((msg: string, kind: Kind = "green", icon = "✓") => {
    const id = ++seq.current;
    setToasts((t) => [...t, { id, msg, kind, icon }]);
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
            <div className="ic" style={{ color: "#fff", fontSize: 14 }}>
              {t.icon}
            </div>
            <div>{t.msg}</div>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
