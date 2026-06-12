/* Global topbar search — pages consume the query and filter their own rows. */
import { createContext, useContext, useState, ReactNode } from "react";

const SearchCtx = createContext<{ query: string; setQuery: (q: string) => void }>({
  query: "",
  setQuery: () => {},
});

export const useSearch = () => useContext(SearchCtx);

export function SearchProvider({ children }: { children: ReactNode }) {
  const [query, setQuery] = useState("");
  return <SearchCtx.Provider value={{ query, setQuery }}>{children}</SearchCtx.Provider>;
}

/** case-insensitive match across any of the given fields */
export function matches(query: string, ...fields: (string | null | undefined)[]): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return fields.some((f) => f && f.toLowerCase().includes(q));
}
