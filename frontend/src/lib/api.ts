const API_URL = (import.meta.env.VITE_API_URL as string) || "http://localhost:8000";

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
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
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
  stage: string;
  tat_deadline: string | null;
  confirmed: boolean;
  qualified_at: string | null;
  is_test: boolean;
}

export interface ConfirmedData {
  purpose: string | null;
  budget_value_lacs: number | null;
  configuration: string | null;
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
  budget_value_lacs: number;
  configuration: string;
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
  syncLeads: () =>
    request<{ status: string; meta_new: number; listing_new: number }>("/v1/leads/sync", { method: "POST" }),
  confirmLead: (id: string, payload: ConfirmPayload) =>
    request<{ status: string }>(`/v1/leads/${id}/confirm`, { method: "POST", body: JSON.stringify(payload) }),
};
