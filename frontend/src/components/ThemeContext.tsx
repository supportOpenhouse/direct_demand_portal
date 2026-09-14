import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";

type Theme = "light" | "dark";
const KEY = "dd_theme";                       // index.html reads this before first paint
const WIPES = ["ltr", "rtl", "ttb", "btt"] as const;

const Ctx = createContext<{ theme: Theme; toggle: () => void } | null>(null);

function initial(): Theme {
  // Default light regardless of the OS preference — an explicit toggle is what gets
  // remembered. Matches the inline script in index.html; change both or neither.
  return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initial);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(KEY, theme);
  }, [theme]);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    const root = document.documentElement;
    if (!document.startViewTransition) { setTheme(next); return; }
    root.dataset.wipe = WIPES[Math.floor(Math.random() * WIPES.length)];
    const vt = document.startViewTransition(() => {
      // flushSync so the re-render lands before the "new" snapshot is taken. The
      // attribute is set here too because the effect above is passive and would
      // otherwise fire after the snapshot — leaving the wipe revealing the OLD theme.
      flushSync(() => setTheme(next));
      root.setAttribute("data-theme", next);
    });
    vt.finished.finally(() => { delete root.dataset.wipe; });
  }

  return <Ctx.Provider value={{ theme, toggle }}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}
