/* useState whose value is remembered in localStorage, so a filter someone set is
   still there after a refresh, a re-login, or coming back tomorrow.

   Per browser, not per user — the same choice `dd_sidebar_collapsed` makes. Filters
   are a workspace preference, not account data, and scoping them to an identity would
   mean waiting on /me before the first paint just to know which key to read.

   Deliberately NOT synced across tabs via the `storage` event: two tabs open on the
   same page are usually two different lines of enquiry, and having one tab's filter
   change yank the other's list out from under it is worse than letting them diverge
   until the next reload.

   Every access is wrapped: Safari private mode and "block site data" make localStorage
   throw rather than return null, and a filter is never worth breaking the page over —
   it degrades to plain in-component state. */
import { useCallback, useState } from "react";

/* Parsers double as type guards: whatever is in storage was written by an older build
   and cannot be trusted to still match T. `undefined` means "unusable, take the
   initial value", which is also what a corrupt or hand-edited entry lands on. */
export const asString = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined);
export const asStrings = (v: unknown): string[] | undefined =>
  Array.isArray(v) && v.every((x) => typeof x === "string") ? (v as string[]) : undefined;
export const asStringsOrNull = (v: unknown): string[] | null | undefined =>
  v === null ? null : asStrings(v);

function read<T>(key: string, parse: (v: unknown) => T | undefined): T | undefined {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? undefined : parse(JSON.parse(raw));
  } catch {
    return undefined; // unavailable, or a value this build can't read
  }
}

function write(key: string, value: unknown, initial: unknown): void {
  try {
    // back to the default → drop the key instead of storing the default. Keeps the
    // absence of an entry meaning "never chosen", which is what the status filter's
    // null sentinel relies on to keep tracking the default as the data changes.
    if (JSON.stringify(value) === JSON.stringify(initial)) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full or blocked — the in-memory value is still correct */
  }
}

type Setter<T> = (next: T | ((prev: T) => T)) => void;

/** Drop-in useState persisted under `key`. Same signature and semantics, functional
    updates included. `parse` validates what comes back out of storage. */
export function usePersistedState<T>(
  key: string,
  initial: T,
  parse: (v: unknown) => T | undefined,
): [T, Setter<T>] {
  const [val, setVal] = useState<T>(() => {
    const stored = read(key, parse);
    return stored === undefined ? initial : stored;
  });
  const set = useCallback<Setter<T>>(
    (next) => {
      setVal((prev) => {
        const resolved = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        write(key, resolved, initial);
        return resolved;
      });
    },
    // `initial` is a literal at every call site; excluding it keeps the setter stable
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  );
  return [val, set];
}
