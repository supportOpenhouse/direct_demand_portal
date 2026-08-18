// exported for the Live Calls SSE hook, which can't go through request(): it needs the
// raw streaming Response rather than a parsed JSON body
export const API_URL = (import.meta.env.VITE_API_URL as string) || "http://localhost:8000";
export const GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string) || "";

/* Local-only "view as another user".

   sessionStorage, not localStorage, so each TAB carries its own identity — you can
   have three tabs open as three different people at once. localStorage would flip
   every tab together.

   import.meta.env.DEV is replaced at build time, so this whole branch is removed from
   a production bundle: the header cannot be sent by the deployed app even by hand. */
export const DEV_USER_KEY = "dd_dev_user";
export const isDevBuild = import.meta.env.DEV;
export const getDevUser = () => (isDevBuild ? sessionStorage.getItem(DEV_USER_KEY) : null);
export const setDevUser = (email: string | null) => {
  if (!isDevBuild) return;
  email ? sessionStorage.setItem(DEV_USER_KEY, email) : sessionStorage.removeItem(DEV_USER_KEY);
};

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
  lead_rm?: string | null;
  rm_accompanying?: string | null;
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

/* Huvo call log — one row per completed call their bot made, with the analytics it
   produced. Distinct from the Bonvoice log, which records telephony legs. */
export interface HuvoCall {
  id: string;
  // call_details.campaign_name, falling back to the CSV import's Campaign column
  campaign_name: string | null;
  from_number: string | null;
  caller_name: string | null;
  call_outcome: string | null;   // 16-value enum; null on rows recording no call
  is_interested: string | null;  // yes | no | unsure
  rsvp_status: string | null;
  lead_score: number | null;     // 0–10
  budget_lacs: number | null;    // converted from their budget_crores string
  summary: string | null;
  recording_url: string | null;
  duration_sec: number | null;
  started_at: string | null;
  received_at: string;
  lead_id: string | null;        // null = no lead for this number yet
  lead_name: string | null;
  lead_stage: string | null;
}

/* Free-text campaign names mean "" can't stand for "no campaign" — it's the same as
   "no filter". Must match NO_CAMPAIGN in backend/app/routers/huvo_calls.py. */
export const NO_CAMPAIGN = "__none__";

export interface HuvoCallDetail extends HuvoCall {
  dedupe_key: string;
  ended_at: string | null;
  follow_up_at: string | null;
  payload: {
    status?: string;
    call_details?: Record<string, unknown>;
    analytics_data?: Record<string, unknown>;
    _import?: { source_file?: string; extra?: Record<string, string> };
  };
}

export interface HuvoBulkLeadReq {
  phones?: string[];        // an explicit tick-box selection
  all_matching?: boolean;   // ...or every unlinked call matching the filters below
  q?: string;
  outcome?: string;
  interested?: string;
  duration?: string;
  campaign?: string;
}

export interface HuvoCallQuery {
  q?: string;
  outcome?: string;
  interested?: string;
  campaign?: string;             // exact name, or NO_CAMPAIGN for "no campaign"
  linked?: string;               // "linked" | "unlinked"
  duration?: string;             // a DURATION_OPTIONS label
  limit?: number;
  offset?: number;
}

/* Org-wide settings: an admin sets them on Settings & Access, everyone reads them.
   Absent keys come back as their default, so this is always fully populated. */
export interface AppSettings {
  // Lead numbers in the New Leads / Follow-up / segment tables — for shared screens
  // and screenshots. The number still reaches the browser and calling still works;
  // this only stops it being rendered.
  hide_lead_phones: boolean;
}

/* Live Calls — the RM's own view of the campaign dialling them. */

export interface LiveCallLead {
  id: string;        // dial_queue row id — what a disposition is stamped against
  lead_id: string;
  name: string | null;
  phone?: string | null;
  society: string | null;
  city: string | null;
  configuration?: string | null;
  budget?: string | null;
  stage?: string | null;
  position?: number;
  dialed_at?: string | null;
  ended_at?: string | null;
  attempts?: number;
  answered?: boolean;
  outcome?: string | null;      // what the PBX reported
  call_result?: string | null;  // what the RM said — null renders "needs result"
  call_result_at?: string | null;
  miss_count?: number;
  ever_connected?: boolean;
}

export interface MyCallsResponse {
  campaign: { id: string; name: string; strategy: string;
              window_start: string; window_end: string } | null;
  // under round_robin/least_load the queue is a shared pool — the next lead in it may
  // ring somebody else's phone, and the page has to say so rather than imply ownership
  upcoming_is_shared: boolean;
  now_calling: LiveCallLead | null;
  upcoming: LiveCallLead[];
  completed: LiveCallLead[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      // dev only; the server ignores it unless auth is off AND APP_ENV isn't prod
      ...(getDevUser() ? { "X-Dev-User": getDevUser() as string } : {}),
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
  follow_up_since: string | null; // when it first entered Follow-up (for "moved here today")
  miss_count: number;           // consecutive not-connected calls (resets on connect)
  last_no_timestamp: string | null;  // last "No" — drives the 2h spam cooldown
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
  follow_up_at: string | null;  // UTC ISO; null = save details only (Pipeline, no callback)
  qualify: boolean;       // true → qualify the lead; false → save details (+ follow-up if given)
}

export interface LeadCountsResponse {
  status: string;
  counts: Record<string, number>; // segment -> count
  total: number; // role-scoped total leads (incl. test), the sidebar % denominator
  total_nontest: number; // same, excluding is_test leads (matches Analytics)
}

/* Raw Gupshup callback as stored by the webhook. `body` is deliberately untyped —
   the whole point of this phase is to see the real shapes before modelling them. */
export interface GupshupEvent {
  received_at: string;
  type: string | null; // message | message-event | user-event | system-event | billing-event
  body: Record<string, any>;
}

/* What a WhatsApp number turned out to be, marked by hand from the chat. */
export type WaTag = "broker" | "buyer" | "seller" | "rejected";
export const WA_TAGS: WaTag[] = ["broker", "buyer", "seller", "rejected"];

export interface WaMessage {
  id: string;
  direction: "in" | "out";
  phone: string;
  name: string | null;
  body: string | null;
  msg_type: string;
  status: string | null;   // submitted | sent | delivered | read | failed (outbound)
  author: string | null;   // portal user who sent it
  media_url: string | null;      // temporary Gupshup link — dead after media_expiry
  media_expiry: string | null;
  media_name: string | null;     // documents carry a filename
  created_at: string;
}

export const api = {
  inventory: () => request<InventoryResponse>("/v1/inventory"),
  gupshupRecent: () => request<{ count: number; items: GupshupEvent[] }>("/v1/gupshup/recent"),
  waMessages: (phone?: string) =>
    request<{
      status: string; send_enabled: boolean;
      leads: Record<string, { id: string; name: string | null }>;  // last-10-digits → lead
      tags: Record<string, WaTag>;                                 // last-10-digits → mark
      owners: Record<string, string>;                              // last-10-digits → owning RM
      items: WaMessage[];
    }>("/v1/gupshup/messages" + (phone ? `?phone=${encodeURIComponent(phone)}` : "")),
  waAssign: (phone: string, assigned_to: string | null) =>
    request<{ status: string; assigned_to: string | null }>("/v1/gupshup/assign", {
      method: "POST", body: JSON.stringify({ phone, assigned_to }),
    }),
  waBackfillAssign: () =>
    request<{ status: string; assigned: number }>("/v1/gupshup/assign/backfill", { method: "POST" }),
  waMark: (phone: string, tag: WaTag) =>
    request<{ status: string; phone10: string; tag: WaTag }>("/v1/gupshup/mark", {
      method: "POST", body: JSON.stringify({ phone, tag }),
    }),
  waLatest: () => request<{ last_inbound_at: string | null }>("/v1/gupshup/latest"),
  /* Bulk: names are resolved server-side, so the client only sends which
     conversations to convert. Leads are created unassigned; already-lead contacts are
     skipped, not duplicated. */
  waBulkCreateLeads: (phones: string[]) =>
    request<{ status: string; created: number; skipped_existing: number;
              requested: number }>("/v1/gupshup/leads/bulk", {
      method: "POST", body: JSON.stringify({ phones }),
    }),
  waCreateLead: (payload: { phone: string; name: string; city?: string; society?: string }) =>
    request<{ status: string; lead_id: string | null }>("/v1/gupshup/leads", {
      method: "POST", body: JSON.stringify(payload),
    }),
  waSend: (phone: string, text: string) =>
    request<{ status: string; gupshup_id: string | null }>("/v1/gupshup/send", {
      method: "POST", body: JSON.stringify({ phone, text }),
    }),
  syncInventory: () =>
    request<{ status: string; rows: number; synced_at: string }>("/v1/inventory/sync", { method: "POST" }),
  supply: () => request<SupplyResponse>("/v1/supply"),
  markPriority: (uid: string, priority: boolean) =>
    request<{ status: string; priority: boolean }>(`/v1/supply/${encodeURIComponent(uid)}/priority`, { method: "POST", body: JSON.stringify({ priority }) }),
  leads: (segment: string) => request<LeadsResponse>(`/v1/leads?segment=${segment}`),
  leadCounts: () => request<LeadCountsResponse>("/v1/leads/counts"),
  lead: (id: string) => request<LeadDetail>(`/v1/leads/${id}`),
  leadMatches: (id: string) => request<LeadMatches>(`/v1/leads/${id}/matches`),
  matchPreview: (payload: MatchPreviewReq) =>
    request<LeadMatches>("/v1/leads/match-preview", { method: "POST", body: JSON.stringify(payload) }),
  syncLeads: () =>
    request<{ status: string; meta_new: number; listing_new: number }>("/v1/leads/sync", { method: "POST" }),
  confirmLead: (id: string, payload: ConfirmPayload) =>
    request<{ status: string }>(`/v1/leads/${id}/confirm`, { method: "POST", body: JSON.stringify(payload) }),
  // queueItemId marks this a campaign call placed by the auto-dialer. The server
  // re-verifies the row is the caller's, then waives the 2h "No" cooldown for it —
  // the scheduler chose to dial, not the RM, so the spam guard doesn't apply.
  callResult: (id: string, connected: boolean, reason?: string, notes?: string,
               queueItemId?: string) =>
    request<{ status: string; connected: boolean; moved_to_rnr: boolean; rejected: boolean;
              // a second "No" inside the 2h cooldown is refused: nothing is recorded,
              // miss_count is untouched, and retry_in_minutes says when it reopens
              blocked?: boolean; retry_in_minutes?: number;
              miss_count?: number; follow_up_at?: string | null }>(
      `/v1/leads/${id}/call-result`, {
        method: "POST",
        body: JSON.stringify({ connected, reason, notes, queue_item_id: queueItemId ?? null }),
      }),
  myCalls: () => request<MyCallsResponse>("/v1/dialer/my-calls"),
  huvoCalls: (p: HuvoCallQuery) => {
    const qs = new URLSearchParams();
    Object.entries(p).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") qs.set(k, String(v)); });
    return request<{ items: HuvoCall[]; total: number; unique_leads?: number;
                     unlinked_unique?: number }>(`/v1/huvo/calls?${qs.toString()}`);
  },
  // payload is excluded from the list query (largest column, nothing renders it) but
  // holds nine analytics fields with no column of their own — so the detail view has
  // its own fetch rather than the row being expanded from what the table already has.
  leadHuvoCalls: (leadId: string) =>
    request<{ items: HuvoCallDetail[] }>(`/v1/leads/${leadId}/huvo-calls`),
  huvoCall: (id: string) => request<HuvoCallDetail>(`/v1/huvo/calls/${id}`),
  huvoCallFilters: () =>
    request<{ outcomes: string[]; interest: string[]; campaigns: string[] }>("/v1/huvo/calls/outcomes"),
  // Mirrors waCreateLead. Also back-links every Huvo call from this number, since the
  // webhook only resolves lead_id at write time.
  huvoCreateLead: (payload: { phone: string; name: string; city?: string; society?: string }) =>
    request<{ status: string; lead_id: string | null; calls_linked: number }>(
      "/v1/huvo/leads", { method: "POST", body: JSON.stringify(payload) }),
  /* Names are taken server-side from the stored calls, so this sends only numbers —
     or, with all_matching, only the filters. The filter form exists because "all 845
     unlinked" can't travel as a phone list: the browser would have to page the whole
     table first, and the set would be stale by the time it arrived. */
  huvoBulkCreateLeads: (body: HuvoBulkLeadReq) =>
    request<{ status: string; requested: number; created: number; calls_linked: number }>(
      "/v1/huvo/leads/bulk", { method: "POST", body: JSON.stringify(body) }),
  appSettings: () => request<AppSettings>("/v1/settings"),
  // PATCH not PUT — CORS allow_methods in backend/app/main.py doesn't list PUT
  setAppSetting: (key: keyof AppSettings, value: boolean) =>
    request<Partial<AppSettings>>(`/v1/settings/${key}`, {
      method: "PATCH", body: JSON.stringify({ value }),
    }),
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
  societiesByCity: (city: string) => request<{ items: string[] }>(`/v1/societies/by-city?city=${encodeURIComponent(city)}`),
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
  // Bonvoice call log (admin)
  callLog: (p: CallLogParams) => {
    const qs = new URLSearchParams();
    Object.entries(p).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") qs.set(k, String(v)); });
    return request<CallLogResponse>(`/v1/bonvoice/calls?${qs.toString()}`);
  },
  /* Who has placed calls — server-side, since the page only holds 50 rows at a time. */
  callLogActors: () => request<{ items: string[] }>("/v1/bonvoice/calls/actors"),
  leadCalls: (id: string) => request<{ items: LeadCallRow[] }>(`/v1/leads/${id}/calls`),
  /* Backfill from Bonvoice's own records — the webhook only knows about calls placed
     after it was wired up. Dates are YYYY-MM-DD. */
  syncCallLog: (from: string, to: string) =>
    request<{ fetched: number; stored: number }>(
      `/v1/bonvoice/calls/sync?from=${from}&to=${to}`, { method: "POST" }),
  // users (admin)
  users: () => request<{ items: ManagedUser[] }>("/v1/users"),
  /* The "view as" list, fetched WITHOUT the X-Dev-User header on purpose: /v1/users is
     admin-only, so once you're viewing as an RM the normal call 403s, the dropdown
     empties and you're stranded with no way back. */
  devUserList: async (): Promise<{ items: ManagedUser[] }> => {
    // inert in prod: the object property survives bundling, the request must not
    if (!isDevBuild) return { items: [] };
    // Throws on purpose. Swallowing into an empty list looked like a *successful*
    // fetch of zero users, so react-query cached it and never retried — one attempt
    // made before the API was up left the switcher permanently blank.
    const r = await fetch(`${API_URL}/v1/users`, { headers: { "Content-Type": "application/json" } });
    if (!r.ok) throw new Error(`users ${r.status}`);
    return r.json();
  },
  placeCall: (lead_id: string) =>
    request<{ status: string; event_id: string; rm_phone_masked: string }>("/v1/bonvoice/call", {
      method: "POST", body: JSON.stringify({ lead_id }),
    }),
  createUser: (u: { email: string; name: string; role: string; smid?: number | null; phone?: string | null }) =>
    request<{ id: string; status: string }>("/v1/users", { method: "POST", body: JSON.stringify(u) }),
  updateUser: (id: string, patch: Partial<{ name: string; role: string; active: boolean; smid: number | null; phone: string | null }>) =>
    request<{ status: string }>(`/v1/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteUser: (id: string) => request<{ status: string }>(`/v1/users/${id}`, { method: "DELETE" }),
  reassignUserLeads: (id: string, toUserId: string) =>
    request<{ status: string; moved: number }>(`/v1/users/${id}/reassign`, { method: "POST", body: JSON.stringify({ to_user_id: toUserId }) }),
  forceLogoutAll: () => request<{ status: string }>("/v1/sessions/logout-all", { method: "POST" }),
  // auto-dialer (admin)
  dialerFields: () => request<DialerFields>("/v1/dialer/fields"),
  dialerPreview: (rules: RuleNode, strategy: string, rms: string[]) =>
    request<{ count: number; scoped: boolean }>("/v1/dialer/preview",
      { method: "POST", body: JSON.stringify({ rules, strategy, rms }) }),
  campaigns: () => request<{ items: CampaignRow[] }>("/v1/dialer/campaigns"),
  createCampaign: (c: CampaignIn) =>
    request<{ id: string; queued: number; unowned: number }>("/v1/dialer/campaigns",
      { method: "POST", body: JSON.stringify(c) }),
  campaign: (id: string) => request<CampaignDetail>(`/v1/dialer/campaigns/${id}`),
  campaignAction: (id: string, action: "start" | "pause" | "stop") =>
    request<{ status: string }>(`/v1/dialer/campaigns/${id}/${action}`, { method: "POST" }),
};

/* ── Auto-dialer ───────────────────────────────────────────────────────────
   The rule tree is sent to the server verbatim and compiled to SQL there — the
   field/op whitelist in /v1/dialer/fields is the same one the compiler enforces. */
export type RuleValue = string[] | number | boolean;
export interface RuleCondition {
  id: string;
  type: "condition";
  field: string;
  op: string;
  value: RuleValue;
}
export interface RuleGroup {
  id: string;
  type: "group";
  combinator: "AND" | "OR";
  children: RuleNode[];
}
export type RuleNode = RuleCondition | RuleGroup;

export interface DialerField {
  key: string;
  label: string;
  kind: "multi" | "daterange" | "number" | "bool";
  ops: string[];
  options: string[];
}
export interface DialerRM {
  email: string;
  name: string;
  has_phone: boolean;
  role: string;  // 'rm' | 'test_rm' — test_rm is badged TEST in the picker
}
export interface DialerFields {
  fields: DialerField[];
  rms: DialerRM[];
}

export interface CampaignIn {
  name: string;
  rules: RuleNode;
  rms: string[];
  strategy: string;
  gap_seconds: number;
  window_start: string;
  window_end: string;
  max_attempts: number;
  cooldown_minutes: number;
  start: boolean;
}
export interface CampaignRow {
  id: string;
  name: string;
  status: "draft" | "running" | "paused" | "done";
  strategy: string;
  rms: string[];
  created_at: string;
  started_at: string | null;
  pending: number;
  live: number;
  completed: number;
  total: number;        // every queue row, incl. leads skipped as not-in-pool
  targeted: number;     // leads the campaign was actually pointed at
  unique_leads: number; // leads actually dialled at least once
  total_calls: number;  // sum of attempts — higher than unique_leads once retries run
  connected: number;
}
export interface CampaignFeedRow {
  status: string;
  outcome: string | null;
  detail: string | null;
  /* Bonvoice's id for the call — the handle for `GET /get-autocall-log/{eventID}/`
     when a call's state needs checking against Bonvoice directly. */
  event_id: string | null;
  attempts: number;
  rm_email: string | null;
  dialed_at: string | null;
  ended_at: string | null;
  lead_name: string | null;
  society: string | null;
  lead_id: string;
  answered: boolean | null;
}
export interface CampaignDetail {
  /* The stored campaign row itself — the queue counts live under `stats`, not here. */
  campaign: {
    id: string;
    name: string;
    status: "draft" | "running" | "paused" | "done";
    strategy: string;
    rms: string[];
    rules: RuleNode;
    gap_seconds: number;
    window_start: string;
    window_end: string;
    max_attempts: number;
    cooldown_minutes: number;
    created_at: string;
    started_at: string | null;
  };
  stats: {
    pending: number; live: number; done: number; failed: number; skipped: number;
    total: number;        // every queue row, incl. leads skipped as not-in-pool
    targeted: number;     // leads the campaign was actually pointed at
    unique_leads: number; // leads dialled at least once
    total_calls: number;  // sum of attempts — exceeds unique_leads once retries run
    connected: number;
  };
  per_rm: Record<string, { live: number; done: number }>;
  feed: CampaignFeedRow[];
}

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

/* One call leg as Bonvoice reported it. A bridged call is two rows — leg A is the
   RM's handset, leg B the lead — and the recording rides on whichever leg carried it. */
export interface CallLogRow {
  call_id: string;
  leg: string;
  event_id: string | null;
  lead_id: string | null;
  lead_name: string | null;
  direction: string | null;
  source_number: string | null;
  destination_number: string | null;
  display_number: string | null;
  status: string | null;
  agent_status: string | null;
  answered: boolean;
  start_at: string | null;
  end_at: string | null;
  recording_url: string | null;
  placed_by: string | null;
  /* Which side of From → To the lead matched on. 'to' = we rang them (normal
     outgoing). 'from' = they rang us, so nobody here placed the call. null when
     no lead is attached. */
  lead_side: "from" | "to" | null;
}
export interface CallLogResponse { items: CallLogRow[]; total: number; }
/* One lead's call history, for the lead-detail card. */
export interface LeadCallRow {
  call_id: string;
  leg: string;
  direction: string | null;
  status: string | null;
  agent_status: string | null;
  answered: boolean;
  start_at: string | null;
  end_at: string | null;
  recording_url: string | null;
}
export interface CallLogParams {
  q?: string; answered?: boolean; limit?: number; offset?: number;
  campaign_id?: string;  // Previous Campaigns: only what this campaign dialled
  placed_by?: string;    // an actor email, or the BY_LEAD / UNKNOWN sentinels
  duration?: string;     // one of DURATION_OPTIONS
}

/* Sentinels the server understands for `placed_by`. Neither can collide with a real
   actor — those are all emails, so both lack an '@'. */
export const PLACED_BY_LEAD = "by-lead";
export const PLACED_BY_UNKNOWN = "unknown";
/* Must match DURATION_BUCKETS in routers/bonvoice.py — the label IS the API value. */
export const DURATION_OPTIONS = ["<1 min", "1-3 mins", "3-5 mins", "5+ mins"];
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
  phone: string | null; // mobile that click-to-call rings first
  active: boolean;
  last_login_at: string | null;
  matched_leads: number;
}

// --- Openhouse app visit booking ---
export interface BookingConfig {
  configured: boolean;
  smid: number | null;
  // active users holding an Openhouse SMID — the only valid accompanying RMs
  bookable: { name: string; smid: number }[];
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
  sales_manager_id?: number | null;  // the RM accompanying, not the caller
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
