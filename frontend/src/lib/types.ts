/**
 * Wire types — mirror of docs/API_CONTRACT.md, exact snake_case field names.
 * All timestamps are ISO-8601 UTC strings.
 */

/* ---------- enums ---------- */
export type Role = 'admin' | 'cm' | 'rm';
export type Source =
  | 'meta'
  | 'gads'
  | '99acres'
  | 'magicbricks'
  | 'youtube'
  | 'whatsapp'
  | 'api'
  | 'webhook'
  | 'sheets';
export type Stage =
  | 'new'
  | 'contacted'
  | 'visit_scheduled'
  | 'visit_feedback'
  | 'negotiation'
  | 'won'
  | 'lost'
  | 'future_prospect'
  | 'timepass';
export type PlanToBuy = 'within_30_days' | '1_3_months' | '3_6_months' | 'just_exploring';
export type Purpose = 'self_use' | 'investment';
export type OfficeWilling = 'yes' | 'no' | 'maybe';
export type ReminderType = 'follow_up' | 'visit_schedule' | 'visit_feedback' | 'negotiation';
export type SupplyStage = 'msi' | 'token_paid' | 'negotiating';
export type TatState = 'ok' | 'warn' | 'breach';
export type MatchedOn = 'city' | 'society' | 'budget' | 'config';
export type Segment = 'new' | 'qualified' | 'pipeline' | 'converted';
export type RouteSource = 'est' | 'google';
export type UnitKind = 'inventory' | 'supply';
export type BroadcastMode = 'whatsapp' | 'call_list';

/* ---------- shared shapes ---------- */
export interface User {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  role: Role;
  team_id: string | null;
  team_name: string | null;
  active: boolean;
}

export interface AssignedTo {
  id: string;
  name: string;
}

export interface TatInfo {
  state: TatState | null;
  deadline: string | null;
  minutes_left: number | null;
}

export interface LeadRow {
  id: string;
  name: string;
  phone: string;
  source: Source;
  stage: Stage;
  is_hot: boolean;
  confirmed: boolean;
  city: string | null;
  society: string | null; // from source data
  configuration: string | null; // effective: confirmed over source
  budget_label: string | null; // display: "₹70L – ₹90L" (band) or "₹85L" (confirmed value)
  plan_to_buy: PlanToBuy | null;
  assigned_to: AssignedTo | null;
  tat: TatInfo;
  qualified_at: string | null;
  created_at: string;
}

export interface SourceData {
  budget_band: string | null;
  budget_min_lacs: number | null;
  budget_max_lacs: number | null;
  city: string | null;
  society: string | null;
  configuration: string | null;
  plan_to_buy: PlanToBuy | null;
}

export interface ConfirmedData {
  purpose: Purpose | null;
  budget_value_lacs: number | null;
  configuration: string | null;
  office_willing: OfficeWilling | null;
  office_preferred_date: string | null;
  remark: string | null;
  confirmed_at: string | null;
}

export interface Activity {
  id: string;
  event: string;
  remark: string | null;
  actor_name: string | null;
  created_at: string;
}

export interface Recording {
  id: string;
  visit_id: string | null;
  file_ref: string;
  duration_sec: number;
  recorded_by_name: string | null;
  recorded_at: string;
}

export interface VisitStop {
  seq: number;
  inventory_id: string;
  name: string;
  society: string | null;
}

export interface Visit {
  id: string;
  trip_date: string;
  rm: AssignedTo | null;
  total_km: number;
  total_min: number;
  route_source: RouteSource;
  status: string;
  stops: VisitStop[];
}

export interface LeadDetail extends LeadRow {
  source_data: SourceData;
  confirmed_data: ConfirmedData | null;
  shortlist_societies: string[]; // Q4
  preferred_localities: string[]; // Q5
  activity: Activity[]; // newest first
  recordings: Recording[];
  visits: Visit[];
}

/** Inventory and supply units share this shape. */
export interface Unit {
  id: string;
  name: string;
  society: string | null;
  city: string | null;
  configuration: string | null;
  price_lacs: number | null;
  budget_min_lacs: number | null;
  budget_max_lacs: number | null;
  area_sqft: number | null;
  status: string | null; // inventory only (e.g. available / resale)
  supply_stage: SupplyStage | null; // supply only
  eta: string | null; // supply only
  interest_count: number; // supply only (0 for inventory)
  lat: number | null;
  lng: number | null;
  image_url: string | null;
  ext_source: 'acquired_property' | 'supply_tracker';
}

export interface Match {
  unit: Unit;
  score: number;
  match_pct: number;
  matched_on: MatchedOn[];
}

export interface Metrics {
  new: number;
  qualified: number;
  immediate: number;
  followups_due_today: number;
  pipeline: number;
  converted: number;
}

export interface Reminder {
  id: string;
  lead_id: string;
  lead_name: string;
  type: ReminderType;
  note: string | null;
  due_at: string;
  done: boolean;
  auto_generated: boolean;
}

export interface BucketMember {
  lead: LeadRow;
  score: number;
  match_pct: number;
  matched_on: MatchedOn[];
}

export interface Bucket {
  id: string;
  unit: Unit;
  unit_kind: UnitKind;
  member_count: number;
  members: BucketMember[];
}

export interface SocietyInsight {
  id: string;
  note: string;
  created_by_name: string | null;
  created_at: string;
}

export interface SocietyCard {
  society: string;
  city: string;
  buyers: number;
  hot_buyers: number;
  live_units: number;
  demand_gap: number;
  insights: SocietyInsight[];
}

/* ---------- response envelopes ---------- */
export interface AuthResponse {
  token: string;
  user: User;
}

export interface LeadsResponse {
  items: LeadRow[];
  count: number;
}

export interface SocietyInsightsStats {
  societies_tracked: number;
  total_demand: number;
  live_units: number;
  high_demand_gaps: number;
}

export interface SocietyInsightsResponse {
  stats: SocietyInsightsStats;
  societies: SocietyCard[];
}

/** Reference list rows for Q4 / Q5 (GET /v1/societies, /v1/localities). */
export interface NameCity {
  name: string;
  city: string;
}

export interface IntegrationSetting {
  key: string;
  label: string;
  enabled: boolean;
}

export interface SettingsResponse {
  integrations: IntegrationSetting[];
  api_key_masked: string;
  webhook_url: string;
  assignment_method: string;
}

export interface VisitCreateResponse {
  visit: Visit;
  self_schedule_token: string;
}

export interface RematchResponse {
  buckets: number;
}

export interface BroadcastResponse {
  sent: number;
}

export interface InterestResponse {
  interest_count: number;
}

/* ---------- request payloads ---------- */
export interface IngestPayload {
  name: string;
  phone: string;
  source: Source;
  city?: string | null;
  society?: string | null;
  configuration?: string | null;
  budget_band?: string | null;
  budget_min_lacs?: number | null;
  budget_max_lacs?: number | null;
  plan_to_buy?: PlanToBuy | null;
}

export interface ConfirmPayload {
  purpose: Purpose;
  budget_value_lacs: number;
  configuration: string;
  shortlist_societies: string[];
  preferred_localities: string[];
  office_willing: OfficeWilling;
  office_preferred_date?: string | null;
  remark?: string | null;
}

export interface StageChangePayload {
  to_stage: Stage;
  remark: string;
}

export interface ReminderCreatePayload {
  lead_id: string;
  type: ReminderType;
  note?: string | null;
  due_at: string;
}

export interface VisitCreatePayload {
  trip_date: string;
  stops: { inventory_id: string; seq: number }[];
  total_km: number;
  total_min: number;
  route_source: RouteSource;
}

export interface InsightCreatePayload {
  society: string;
  city: string;
  note: string;
}
