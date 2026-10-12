/* The lead-list search box (LeadToolbar) — plain text as before, plus field search
   `field:"text" AND field2:"text" OR …`, fuzzy-matched against the leads the page already
   holds. Runs in the browser: the lists are client-side everywhere else too. The box's
   Claude mode (admins) is server-side and arrives here as an id set (`LeadSearch`).

   Grammar: clauses joined by AND / OR (any case); AND binds tighter than OR, as in SQL;
   two clauses with nothing between them mean AND. No parentheses. A clause is
   `field:"text"`, `field:word`, or a bare `"text"` (= any field). `field:""` matches
   everything, so a field picked from the dropdown doesn't blank the results before
   anything is typed into it.

   node scripts/check-lead-query.mjs runs the real module against the rules below. */
import type { Lead } from "./api";
import { leadMatchesQuery, srcLabel, stageLabel } from "./leads";

export interface QueryField {
  key: string;
  label: string;
  get: (l: Lead) => (string | null | undefined)[];
  /** offer the field's existing values as you type — off for free text and identifiers */
  suggest?: boolean;
}

const CORE: QueryField[] = [
  { key: "name", label: "Name", get: (l) => [l.name], suggest: true },
  { key: "phone", label: "Phone", get: (l) => [l.phone] },
  { key: "email", label: "Email", get: (l) => [l.email] },
  { key: "city", label: "City", get: (l) => [l.city], suggest: true },
  { key: "society", label: "Society", get: (l) => l.societies ?? [], suggest: true },
  { key: "source", label: "Source", get: (l) => (l.sources?.length ? l.sources : [l.source]).map(srcLabel), suggest: true },
  // label AND key, so `stage:"call back"` and `stage:follow_up` both work
  { key: "stage", label: "Stage", get: (l) => [stageLabel(l.stage), l.stage], suggest: true },
  { key: "warmth", label: "Hot / Warm / Cold", get: (l) => [l.qualified_status], suggest: true },
  { key: "rm", label: "Assigned RM", get: (l) => [l.assigned_to], suggest: true },
  { key: "budget", label: "Budget", get: (l) => [l.budget_band], suggest: true },
  { key: "config", label: "Configuration", get: (l) => [l.configuration], suggest: true },
  { key: "plan", label: "Plan to buy", get: (l) => [l.plan_to_buy], suggest: true },
  { key: "visit_day", label: "Preferred visit day", get: (l) => [l.preferred_visit_day], suggest: true },
  { key: "remarks", label: "Remarks", get: (l) => [l.latest_note, l.source_remarks] },
  { key: "reject", label: "Reject reason / notes", get: (l) => [l.reject_reason, l.reject_notes], suggest: true },
  { key: "visit", label: "Latest visit (society / status / RM)", get: (l) => [l.visit_society, l.visit_status, l.visit_rm], suggest: true },
  { key: "profession", label: "Profession", get: (l) => [l.buyer_profession], suggest: true },
  { key: "property_type", label: "Property type", get: (l) => [l.buyer_property_type], suggest: true },
];

export const QUERY_FIELDS: QueryField[] = [
  ...CORE,
  { key: "any", label: "Any field", get: (l) => CORE.flatMap((f) => f.get(l)) },
];
export const FIELD_BY_KEY: Record<string, QueryField> = Object.fromEntries(QUERY_FIELDS.map((f) => [f.key, f]));

// ── fuzzy ─────────────────────────────────────────────────────────────────────────

const norm = (s: string) => s.toLowerCase().normalize("NFKD").replace(/[^\p{L}\p{N}]+/gu, " ").trim();

/** Edit distance with adjacent swaps counted once ("gurgoan" → "gurgaon" = 1). */
function osa(a: string, b: string): number {
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[a.length][b.length];
}

/** Typos allowed per word: none up to 3 letters (or "rnr" finds everything), 1 to 6, 2 beyond. */
const tolerance = (len: number) => (len <= 3 ? 0 : len <= 6 ? 1 : 2);

/** Does `needle` fuzzily occur in `hay`? Substring first; digits compared as digits (so
    "98765 43" finds "+91 98765 43210"); otherwise every word of the needle must be within
    its typo tolerance of some word of the value — or of that word's same-length prefix,
    so a half-typed "sobah" still finds "Sobha City". */
export function fuzzyMatch(needle: string, hay: string | null | undefined): boolean {
  if (!hay) return false;
  const n = norm(needle), h = norm(hay);
  if (!n) return true;
  if (h.includes(n)) return true;
  const nd = needle.replace(/\D/g, "");
  if (nd.length >= 4 && nd.length === needle.replace(/[\s+()-]/g, "").length && hay.replace(/\D/g, "").includes(nd)) return true;
  const words = h.split(" ");
  return n.split(" ").every((t) => {
    const tol = tolerance(t.length);
    return words.some((w) => w.startsWith(t) || osa(t, w) <= tol || (w.length > t.length && osa(t, w.slice(0, t.length)) <= tol));
  });
}

// ── parse + evaluate ──────────────────────────────────────────────────────────────

export interface Clause { field: string; text: string }
export interface ParsedQuery { groups: Clause[][]; errors: string[] }

// field:"text" | field:"unclosed… | field:word | "text" | AND | OR
const TOKEN = /(\w+)\s*:\s*(?:"([^"]*)"?|([^\s"]*))|"([^"]*)"?|\b(AND|OR)\b|(\S+)/gi;

export function parseQuery(q: string): ParsedQuery {
  const groups: Clause[][] = [[]];
  const errors: string[] = [];
  for (const m of q.matchAll(TOKEN)) {
    const [, field, quoted, word, bare, op, junk] = m;
    if (op) {
      if (op.toUpperCase() === "OR" && groups[groups.length - 1].length) groups.push([]);
      continue;
    }
    if (junk !== undefined) { errors.push(`"${junk}" isn't field:"text" — wrap free text in quotes`); continue; }
    const key = field ? field.toLowerCase() : "any";
    if (!FIELD_BY_KEY[key]) { errors.push(`unknown field "${field}"`); continue; }
    groups[groups.length - 1].push({ field: key, text: (quoted ?? word ?? bare ?? "").trim() });
  }
  return { groups: groups.filter((g) => g.length), errors };
}

const clauseMatches = (l: Lead, c: Clause) =>
  !c.text || FIELD_BY_KEY[c.field].get(l).some((v) => fuzzyMatch(c.text, v));

/** Any OR-group whose every clause matches. An empty query matches every lead. */
export function matchesQuery(l: Lead, p: ParsedQuery): boolean {
  return !p.groups.length || p.groups.some((g) => g.every((c) => clauseMatches(l, c)));
}

// ── what to offer at the cursor ───────────────────────────────────────────────────

export type CursorContext =
  | { kind: "value"; field: string; partial: string; from: number }   // inside field:"…
  | { kind: "field"; partial: string; from: number }                  // typing a field name
  | { kind: "joiner" }                                                // just after a finished clause
  | { kind: "none" };

export function cursorContext(q: string, caret: number): CursorContext {
  const before = q.slice(0, caret);
  const quotes = (before.match(/"/g) ?? []).length;
  if (quotes % 2 === 1) {
    const m = before.match(/(\w+)\s*:\s*"([^"]*)$/);
    return m ? { kind: "value", field: m[1].toLowerCase(), partial: m[2], from: caret - m[2].length } : { kind: "none" };
  }
  // a finished clause right before the cursor: a closed "…" (quotes are even here), or a
  // field:word already followed by a space
  if (/(?:"[^"]*"|\w+\s*:\s*[^\s"]+\s)\s*$/.test(before)) return { kind: "joiner" };
  const w = before.match(/(?:^|\s)(\w*)$/);
  if (w && !/^(AND|OR)$/i.test(w[1])) {
    const atStart = /^\s*$/.test(before.slice(0, caret - w[1].length)) || /\b(AND|OR)\s+$/i.test(before.slice(0, caret - w[1].length));
    if (w[1] || atStart) return { kind: "field", partial: w[1], from: caret - w[1].length };
  }
  return { kind: "none" };
}

/** Field names for a half-typed one: key or label prefix, then anywhere in the label. */
export function fieldSuggestions(partial: string): QueryField[] {
  const p = partial.toLowerCase();
  if (!p) return QUERY_FIELDS;
  const starts = QUERY_FIELDS.filter((f) => f.key.startsWith(p) || f.label.toLowerCase().startsWith(p));
  const inside = QUERY_FIELDS.filter((f) => !starts.includes(f) && f.label.toLowerCase().includes(p));
  return [...starts, ...inside];
}

/** The field's existing values that fit what's typed so far, most common first. */
export function valueSuggestions(leads: Lead[], field: string, partial: string, limit = 8): { value: string; count: number }[] {
  const f = FIELD_BY_KEY[field];
  if (!f?.suggest) return [];
  const counts = new Map<string, { value: string; count: number }>();
  for (const l of leads) {
    for (const v of new Set(f.get(l))) {
      if (!v || !fuzzyMatch(partial, v)) continue;
      const k = v.toLowerCase();
      const e = counts.get(k) ?? { value: v, count: 0 };
      e.count++;
      counts.set(k, e);
    }
  }
  return [...counts.values()].sort((a, b) => b.count - a.count || a.value.localeCompare(b.value)).slice(0, limit);
}

// ── the applied search a lead page filters by ─────────────────────────────────────

/** What a lead page filters by. `claudeIds` set = a Claude search's matches (the text is
    kept only to show and log it); otherwise `q` is a typed search. */
export interface LeadSearch { q: string; claudeIds: Set<string> | null }
export const NO_SEARCH: LeadSearch = { q: "", claudeIds: null };

// one parse per query, not one per lead per render
let lastQ = "";
let lastParsed: ParsedQuery = { groups: [], errors: [] };
const parsed = (q: string) => (q === lastQ ? lastParsed : ((lastQ = q), (lastParsed = parseQuery(q))));

/** Field syntax when the box holds a valid `field:"…"` / `"…"` query; anything else — a
    name, a phone, "Sahaj: 1709" — is the plain any-field search it always was. */
export function leadMatchesSearch(s: LeadSearch, l: Lead): boolean {
  if (s.claudeIds) return s.claudeIds.has(l.id);
  if (!s.q) return true;
  if (/\w+\s*:|"/.test(s.q)) {
    const p = parsed(s.q);
    if (!p.errors.length && p.groups.length) return matchesQuery(l, p);
  }
  return leadMatchesQuery(s.q, l);
}
