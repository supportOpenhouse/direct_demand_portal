const API_URL = (import.meta.env.VITE_API_URL as string) || "http://localhost:8000";
export const GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string) || "";

const TOKEN_KEY = "dd_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string | null) =>
  t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);

export interface InventoryItem {
  id: number;
  name: string | null;
  society: string | null;
  locality: string | null;
  city: string | null;
  configuration: string | null;
  area_sqft: number | null;
  price_text: string | null;
  price_lacs: number | null;
  status: string | null;
  image_url: string | null;
  raw: Record<string, unknown>; // full sheet row + images[] from the photos API
}

export interface InventoryResponse {
  status: "ok" | "not_configured" | "error";
  last_synced_at: string | null;
  detail: string | null;
  items: InventoryItem[];
}

export interface SupplyItem {
  id: string;
  name: string | null;
  society: string | null;
  locality: string | null;
  city: string | null;
  stage: string;
  stage_key: string;
  configuration: string | null;
  area_sqft: number | null;
  price_text: string | null;
  price_lacs: number | null;
  image_url: string | null;
  raw: Record<string, string | null>;
}

export interface SupplyResponse {
  status: "ok" | "not_configured" | "unavailable";
  detail: string | null;
  items: SupplyItem[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
  });
  if (res.status === 401) {
    setToken(null);
    if (GOOGLE_CLIENT_ID) window.location.reload(); // bounce to login gate
    throw new Error("session expired");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  picture: string | null;
  role: string;
}

export interface DashboardMetrics {
  status: string;
  totals: { new: number; qualified: number; pipeline: number; converted: number; immediate: number; unassigned: number; confirmed_total: number; total: number };
  conversion_rate: number;
  by_source: { source: string; c: number }[];
  by_city: { city: string; c: number }[];
  by_stage: { stage: string; c: number }[];
  by_assignee: { name: string; c: number }[];
  by_day: { day: string; c: number }[];
  recent: { id: string; name: string | null; source: string; city: string | null; society: string | null; stage: string; assigned_to: string | null; received_at: string | null }[];
}

export interface Lead {
  id: string;
  source_category: "meta" | "listing";
  source: string; // 'meta' | '99acres' | 'magicbricks'
  name: string | null;
  phone: string | null;
  email: string | null;
  assigned_to: string | null;
  city: string | null;
  society: string | null;
  configuration: string | null;
  budget_band: string | null;
  plan_to_buy: string | null;
  preferred_visit_day: string | null;
  source_remarks: string | null;
  source_meta: Record<string, unknown>;
  received_at: string | null;
  stage: string;
  tat_deadline: string | null;
  confirmed: boolean;
  qualified_at: string | null;
  is_test: boolean;
}

export interface MatchUnit {
  id: string;
  name: string | null;
  society: string | null;
  locality: string | null;
  city: string | null;
  configuration: string | null;
  area_sqft: number | null;
  price_text: string | null;
  price_lacs: number | null;
  status?: string | null;
  stage?: string;
  stage_key?: string;
  image_url?: string | null;
  score: number;
  matched_on: string[];
}

export interface LeadMatches {
  requirement: { city: string | null; societies: string[]; config: string | null; bmin: number | null; bmax: number | null };
  inventory: MatchUnit[];
  supply: MatchUnit[];
}

export interface MatchPreviewReq {
  city?: string | null;
  societies?: string[];
  localities?: string[];
  micromarkets?: string[];
  configuration?: string | null;
  size_min_sqft?: number | null;
  size_max_sqft?: number | null;
  budget_min_lacs?: number | null;
  budget_max_lacs?: number | null;
  budget_band?: string | null;
}

export interface ConfirmedData {
  purpose: string | null;
  budget_min_lacs: number | null;
  budget_max_lacs: number | null;
  configuration: string | null;
  size_min_sqft: number | null;
  size_max_sqft: number | null;
  preferred_micromarkets: string[];
  shortlisted_societies: string[];
  preferred_localities: string[];
  office_willing: string | null;
  office_preferred_date: string | null;
  remark: string | null;
  confirmed_at: string | null;
}

export type LeadDetail = Lead & { confirmed_data: ConfirmedData | null };

export interface LeadsResponse {
  status: "ok" | "not_configured" | "error";
  detail: string | null;
  items: Lead[];
  sync: { listing: SyncMeta | null; meta: SyncMeta | null } | null;
}
interface SyncMeta {
  last_synced_at: string | null;
  last_status: string | null;
  detail: string | null;
  row_count: number | null;
}

export interface ConfirmPayload {
  purpose: string;
  budget_min_lacs: number;
  budget_max_lacs: number;
  configuration: string;
  size_min_sqft: number | null;
  size_max_sqft: number | null;
  preferred_micromarkets: string[];
  shortlisted_societies: string[];
  preferred_localities: string[];
  office_willing: string;
  office_preferred_date: string | null;
  remark: string | null;
}

export const api = {
  inventory: () => request<InventoryResponse>("/v1/inventory"),
  syncInventory: () =>
    request<{ status: string; rows: number; synced_at: string }>("/v1/inventory/sync", { method: "POST" }),
  supply: () => request<SupplyResponse>("/v1/supply"),
  leads: (segment: string) => request<LeadsResponse>(`/v1/leads?segment=${segment}`),
  lead: (id: string) => request<LeadDetail>(`/v1/leads/${id}`),
  leadMatches: (id: string) => request<LeadMatches>(`/v1/leads/${id}/matches`),
  matchPreview: (payload: MatchPreviewReq) =>
    request<LeadMatches>("/v1/leads/match-preview", { method: "POST", body: JSON.stringify(payload) }),
  syncLeads: () =>
    request<{ status: string; meta_new: number; listing_new: number }>("/v1/leads/sync", { method: "POST" }),
  confirmLead: (id: string, payload: ConfirmPayload) =>
    request<{ status: string }>(`/v1/leads/${id}/confirm`, { method: "POST", body: JSON.stringify(payload) }),
  authGoogle: (credential: string) =>
    request<{ token: string; user: AuthUser }>("/v1/auth/google", { method: "POST", body: JSON.stringify({ credential }) }),
  me: () => request<AuthUser>("/v1/me"),
  dashboard: () => request<DashboardMetrics>("/v1/metrics/dashboard"),
  // source-captured edit + notes thread + autocomplete
  patchSourceData: (id: string, patch: Partial<Record<"city" | "society" | "configuration" | "budget_band" | "plan_to_buy" | "source_remarks", string>>) =>
    request<{ status: string }>(`/v1/leads/${id}/source-data`, { method: "PATCH", body: JSON.stringify(patch) }),
  leadNotes: (id: string) => request<{ items: LeadNote[] }>(`/v1/leads/${id}/notes`),
  addNote: (id: string, body: string) =>
    request<{ status: string }>(`/v1/leads/${id}/notes`, { method: "POST", body: JSON.stringify({ body }) }),
  searchSocieties: (q: string) => request<{ items: SocietyHit[] }>(`/v1/societies/search?q=${encodeURIComponent(q)}`),
  searchLocalities: (q: string) => request<{ items: string[] }>(`/v1/localities/search?q=${encodeURIComponent(q)}`),
  searchMicromarkets: (q: string) => request<{ items: { micro_market: string; city: string | null }[] }>(`/v1/micromarkets/search?q=${encodeURIComponent(q)}`),
  localitiesByMicromarket: (mm: string) => request<{ items: string[] }>(`/v1/localities/by-micromarket?micro_market=${encodeURIComponent(mm)}`),
  societiesByLocality: (loc: string) => request<{ items: string[] }>(`/v1/societies/by-locality?locality=${encodeURIComponent(loc)}`),
  assignees: () => request<{ items: { name: string; email: string }[] }>("/v1/assignees"),
  assignLead: (id: string, assigned_to: string | null) =>
    request<{ status: string; assigned_to: string | null }>(`/v1/leads/${id}/assign`, { method: "POST", body: JSON.stringify({ assigned_to }) }),
  // users (admin)
  users: () => request<{ items: ManagedUser[] }>("/v1/users"),
  createUser: (u: { email: string; name: string; role: string }) =>
    request<{ id: string; status: string }>("/v1/users", { method: "POST", body: JSON.stringify(u) }),
  updateUser: (id: string, patch: Partial<{ name: string; role: string; active: boolean }>) =>
    request<{ status: string }>(`/v1/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteUser: (id: string) => request<{ status: string }>(`/v1/users/${id}`, { method: "DELETE" }),
};

export interface LeadNote {
  id: string | null;
  body: string;
  author: string | null;
  source: "remarks" | "note";
  created_at: string | null;
}
export interface SocietyHit {
  society: string;
  locality: string | null;
  city: string | null;
  micro_market: string | null;
}
export interface ManagedUser {
  id: string;
  email: string;
  name: string | null;
  picture: string | null;
  role: string;
  maps_to: string | null; // first name we match against the sheet's "Assigned to"
  active: boolean;
  last_login_at: string | null;
  matched_leads: number;
}
