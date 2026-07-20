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
  lat: number | null;
  lng: number | null;
  raw: Record<string, unknown>; // full sheet row + images[] from the photos API
}

export interface VisitStop {
  inventory_id?: number | null;
  name?: string | null;
  society?: string | null;
  locality?: string | null;
  price_text?: string | null;
  lat?: number | null;
  lng?: number | null;
}
export interface VisitPlan {
  trip_date?: string | null;
  rm?: string | null;
  start_lat?: number | null;
  start_lng?: number | null;
  total_km?: number | null;
  total_min?: number | null;
  route_source?: string | null;
  stops: VisitStop[];
  created_at?: string | null;
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
  // OH reference price matched by society + area (±5); see services/pricing.py
  oh_price_lacs: number | null;
  price_status: "match" | "area_off" | "no_area" | "no_match" | string;
  price_reason: string | null;
  price_tooltip: string | null;
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
  created_at: string | null;
  stage: string;
  tat_deadline: string | null;
  reject_reason: string | null;
  reject_notes: string | null;
  rejected_at: string | null;
  confirmed: boolean;
  qualified_at: string | null;
  follow_up_at: string | null;  // next callback due (UTC); set → lead is in the Follow-up tab
  miss_count: number;           // consecutive not-connected calls (resets on connect)
  ever_connected: boolean;      // have we ever connected? gates RNR escalation
  is_hot: boolean;              // starred as a hot lead
  visit_status: "upcoming" | "completed" | "cancelled" | null;  // latest booked visit
  visit_date: string | null;    // its scheduled date
  visit_count: number;          // visits booked on the Openhouse app
  latest_note: string | null;   // newest note/remark, for the inline notes column
  latest_note_at: string | null; // timestamp of the newest manual note (for sorting)
  note_count: number;           // total notes + source remarks
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
  priority?: boolean;
  // OH price match state (supply units only); price_lacs already holds the OH price when matched
  price_status?: "match" | "area_off" | "no_area" | "no_match" | string;
  price_reason?: string | null;
  price_tooltip?: string | null;
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
  follow_up_at: string;   // mandatory — UTC ISO; a follow-up is required to confirm/save
  qualify: boolean;       // true → qualify the lead; false → save details + follow-up only
}

export const api = {
  inventory: () => request<InventoryResponse>("/v1/inventory"),
  syncInventory: () =>
    request<{ status: string; rows: number; synced_at: string }>("/v1/inventory/sync", { method: "POST" }),
  supply: () => request<SupplyResponse>("/v1/supply"),
  markPriority: (uid: string, priority: boolean) =>
    request<{ status: string; priority: boolean }>(`/v1/supply/${encodeURIComponent(uid)}/priority`, { method: "POST", body: JSON.stringify({ priority }) }),
  leads: (segment: string) => request<LeadsResponse>(`/v1/leads?segment=${segment}`),
  lead: (id: string) => request<LeadDetail>(`/v1/leads/${id}`),
  leadMatches: (id: string) => request<LeadMatches>(`/v1/leads/${id}/matches`),
  matchPreview: (payload: MatchPreviewReq) =>
    request<LeadMatches>("/v1/leads/match-preview", { method: "POST", body: JSON.stringify(payload) }),
  syncLeads: () =>
    request<{ status: string; meta_new: number; listing_new: number }>("/v1/leads/sync", { method: "POST" }),
  confirmLead: (id: string, payload: ConfirmPayload) =>
    request<{ status: string }>(`/v1/leads/${id}/confirm`, { method: "POST", body: JSON.stringify(payload) }),
  callResult: (id: string, connected: boolean) =>
    request<{ status: string; connected: boolean; moved_to_rnr: boolean; miss_count?: number }>(
      `/v1/leads/${id}/call-result`, { method: "POST", body: JSON.stringify({ connected }) }),
  setFollowup: (id: string, followUpAt: string) =>
    request<{ status: string }>(`/v1/leads/${id}/followup`, { method: "POST", body: JSON.stringify({ follow_up_at: followUpAt }) }),
  leadCrmVisits: (id: string) => request<{ items: CrmVisitRow[] }>(`/v1/leads/${id}/crm-visits`),
  markHot: (id: string, hot: boolean) =>
    request<{ status: string; is_hot: boolean }>(`/v1/leads/${id}/hot`, { method: "POST", body: JSON.stringify({ hot }) }),
  syncVisits: () =>
    request<{ status: string; checked: number; updated: number }>("/v1/visits/sync", { method: "POST" }),
  rejectLead: (id: string, reason: string, notes: string) =>
    request<{ status: string }>(`/v1/leads/${id}/reject`, { method: "POST", body: JSON.stringify({ reason, notes }) }),
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
  saveVisit: (id: string, plan: VisitPlan) =>
    request<{ status: string }>(`/v1/leads/${id}/visits`, { method: "POST", body: JSON.stringify(plan) }),
  // Openhouse app visit booking
  bookingConfig: () => request<BookingConfig>("/v1/visits/booking-config"),
  bookVisits: (payload: BookRequest) =>
    request<BookResponse>("/v1/visits/book", { method: "POST", body: JSON.stringify(payload) }),
  latestVisit: (id: string) => request<{ plan: VisitPlan | null }>(`/v1/leads/${id}/visits`),
  assignees: () => request<{ items: { name: string; email: string }[] }>("/v1/assignees"),
  assignLead: (id: string, assigned_to: string | null) =>
    request<{ status: string; assigned_to: string | null }>(`/v1/leads/${id}/assign`, { method: "POST", body: JSON.stringify({ assigned_to }) }),
  bulkAssign: (lead_ids: string[], assigned_to: string | null) =>
    request<{ status: string; updated: number; assigned_to: string | null }>("/v1/leads/bulk-assign", { method: "POST", body: JSON.stringify({ lead_ids, assigned_to }) }),
  // audit logs (admin)
  logs: (p: LogsParams) => {
    const qs = new URLSearchParams();
    Object.entries(p).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") qs.set(k, String(v)); });
    return request<LogsResponse>(`/v1/logs?${qs.toString()}`);
  },
  logActors: () => request<{ items: string[] }>("/v1/logs/actors"),
  // users (admin)
  users: () => request<{ items: ManagedUser[] }>("/v1/users"),
  createUser: (u: { email: string; name: string; role: string; smid?: number | null }) =>
    request<{ id: string; status: string }>("/v1/users", { method: "POST", body: JSON.stringify(u) }),
  updateUser: (id: string, patch: Partial<{ name: string; role: string; active: boolean; smid: number | null }>) =>
    request<{ status: string }>(`/v1/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteUser: (id: string) => request<{ status: string }>(`/v1/users/${id}`, { method: "DELETE" }),
  reassignUserLeads: (id: string, toUserId: string) =>
    request<{ status: string; moved: number }>(`/v1/users/${id}/reassign`, { method: "POST", body: JSON.stringify({ to_user_id: toUserId }) }),
};

/** One visit booked on the Openhouse app. A lead can have many — each its own visit id. */
export interface CrmVisitRow {
  visit_id: number;
  home_id: number | null;
  society: string | null;
  city: string | null;
  selected_date: string | null;
  selected_time: string | null;
  status: "upcoming" | "completed" | "cancelled";
  visit_date: string | null;
  buyer_feedback: string | null;
  sales_feedback: string | null;
  booked_by: string | null;
}

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
export interface AuditLogRow {
  id: string;
  created_at: string | null;
  actor_email: string | null;
  actor_name: string | null;
  actor_role: string | null;
  action: string;
  category: "auth" | "write" | "read" | string;
  method: string;
  path: string;
  status_code: number | null;
  duration_ms: number | null;
  ip: string | null;
}
export interface LogsResponse { items: AuditLogRow[]; total: number; }
export interface LogsParams {
  actor?: string; category?: string; method?: string; q?: string;
  status?: number; from?: string; to?: string; limit?: number; offset?: number;
}

export interface ManagedUser {
  id: string;
  email: string;
  name: string | null;
  picture: string | null;
  role: string;
  maps_to: string | null; // first name we match against the sheet's "Assigned to"
  smid: number | null; // Openhouse SalesManager id (required to book visits)
  active: boolean;
  last_login_at: string | null;
  matched_leads: number;
}

// --- Openhouse app visit booking ---
export interface BookingConfig {
  configured: boolean;
  smid: number | null;
  can_book: boolean;
  default_source: string;
  city_cp: Record<string, { cp_id: number; label: string }>;
}
export interface BookVisitIn {
  home_id: number;
  city: string | null;
  buyer_name: string;
  buyer_mobile: string;
  society?: string | null;
}
export interface BookRequest {
  selected_date: string;
  selected_time: string;
  source: string;
  lead_id?: string | null;   // links the booking to a lead → drives the Pipeline tab
  visits: BookVisitIn[];
}
export interface BookResultRow {
  home_id: number;
  ok: boolean;
  visit_id?: number;
  error?: string;
  remaining_days?: number;
}
export interface BookResponse {
  booked: number;
  failed: number;
  results: BookResultRow[];
}
