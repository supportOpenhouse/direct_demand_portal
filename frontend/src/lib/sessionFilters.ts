/* Session-scoped, in-memory sticky state for per-page filters.

   Why a module-level Map and not localStorage: the filters should be remembered while
   you move between pages WITHIN a session, and reset on a page refresh. A module
   variable is exactly that — it survives a route change (the page unmounts and
   remounts, this module stays loaded) and is wiped on a full reload, when the JS is
   re-evaluated. Nothing is persisted, so it only ever affects the current tab. */
import { useCallback, useState } from "react";

const store = new Map<string, unknown>();

export const readSticky = <T,>(key: string, fallback: T): T =>
  (store.has(key) ? (store.get(key) as T) : fallback);
export const writeSticky = <T,>(key: string, value: T): void => {
  store.set(key, value);
};

type Setter<T> = (next: T | ((prev: T) => T)) => void;

/** Drop-in useState whose value is remembered (in memory) under `key` across
    unmount/remount. Same signature, functional updates included. */
export function useStickyState<T>(key: string, initial: T): [T, Setter<T>] {
  const [val, setVal] = useState<T>(() => readSticky(key, initial));
  const set = useCallback<Setter<T>>(
    (next) => {
      setVal((prev) => {
        const resolved = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        writeSticky(key, resolved);
        return resolved;
      });
    },
    [key],
  );
  return [val, set];
}
