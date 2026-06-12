/**
 * React Query hooks for every API_CONTRACT.md endpoint.
 *
 * Conventions:
 * - queryKeys holds every cache key; invalidation always uses key prefixes
 *   (e.g. ['leads'] invalidates every segment).
 * - Lead-scoped mutations take the lead id as the hook argument
 *   (useConfirmLead(leadId)) so LeadDetail-page usage is ergonomic; list-row
 *   mutations (useUpdateReminder, useAddInterest, useBroadcast) take the id
 *   in the mutation variables instead.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import type {
  AuthResponse,
  BroadcastMode,
  BroadcastResponse,
  Bucket,
  ConfirmPayload,
  IngestPayload,
  InsightCreatePayload,
  InterestResponse,
  LeadDetail,
  LeadRow,
  LeadsResponse,
  Match,
  Metrics,
  NameCity,
  Reminder,
  ReminderCreatePayload,
  ReminderType,
  RematchResponse,
  Segment,
  SettingsResponse,
  SocietyInsight,
  SocietyInsightsResponse,
  SourceData,
  StageChangePayload,
  Unit,
  UnitKind,
  User,
  VisitCreatePayload,
  VisitCreateResponse,
} from './types';

/* ------------------------------------------------------------------ */
/* query keys                                                          */
/* ------------------------------------------------------------------ */

export const queryKeys = {
  me: ['me'] as const,
  metrics: ['metrics'] as const,
  leads: (segment: Segment) => ['leads', segment] as const,
  lead: (id: string) => ['lead', id] as const,
  matches: (id: string, kind: UnitKind) => ['matches', id, kind] as const,
  reminders: (type?: ReminderType) => ['reminders', type ?? 'all'] as const,
  inventory: ['inventory'] as const,
  supply: ['supply'] as const,
  buckets: ['buckets'] as const,
  societyInsights: ['societyInsights'] as const,
  societies: ['societies'] as const,
  localities: ['localities'] as const,
  users: ['users'] as const,
  settings: ['settings'] as const,
};

/* ------------------------------------------------------------------ */
/* queries                                                             */
/* ------------------------------------------------------------------ */

export function useMe(enabled = true) {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: () => api.get<User>('/me'),
    enabled,
  });
}

export function useMetrics() {
  return useQuery({
    queryKey: queryKeys.metrics,
    queryFn: () => api.get<Metrics>('/metrics/dashboard'),
  });
}

export function useLeads(segment: Segment) {
  return useQuery({
    queryKey: queryKeys.leads(segment),
    queryFn: () => api.get<LeadsResponse>(`/leads?segment=${segment}`),
  });
}

export function useLead(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.lead(id ?? ''),
    queryFn: () => api.get<LeadDetail>(`/leads/${id}`),
    enabled: !!id,
  });
}

export function useMatches(id: string | undefined, kind: UnitKind) {
  return useQuery({
    queryKey: queryKeys.matches(id ?? '', kind),
    queryFn: () => api.get<Match[]>(`/leads/${id}/matches/${kind}`),
    enabled: !!id,
  });
}

export function useReminders(type?: ReminderType) {
  return useQuery({
    queryKey: queryKeys.reminders(type),
    queryFn: () => api.get<Reminder[]>(`/reminders${type ? `?type=${type}` : ''}`),
  });
}

export function useInventory() {
  return useQuery({
    queryKey: queryKeys.inventory,
    queryFn: () => api.get<Unit[]>('/inventory'),
  });
}

export function useSupply() {
  return useQuery({
    queryKey: queryKeys.supply,
    queryFn: () => api.get<Unit[]>('/supply'),
  });
}

/** Gold Mine buckets — pass {enabled:false} for roles without access (RM). */
export function useBuckets(opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.buckets,
    queryFn: () => api.get<Bucket[]>('/buckets'),
    enabled: opts?.enabled ?? true,
  });
}

export function useSocietyInsights() {
  return useQuery({
    queryKey: queryKeys.societyInsights,
    queryFn: () => api.get<SocietyInsightsResponse>('/societies/insights'),
  });
}

export function useSocieties() {
  return useQuery({
    queryKey: queryKeys.societies,
    queryFn: () => api.get<NameCity[]>('/societies'),
    staleTime: 5 * 60_000,
  });
}

export function useLocalities() {
  return useQuery({
    queryKey: queryKeys.localities,
    queryFn: () => api.get<NameCity[]>('/localities'),
    staleTime: 5 * 60_000,
  });
}

export function useUsers() {
  return useQuery({
    queryKey: queryKeys.users,
    queryFn: () => api.get<User[]>('/users'),
  });
}

export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: () => api.get<SettingsResponse>('/settings'),
  });
}

/* ------------------------------------------------------------------ */
/* mutations                                                           */
/* ------------------------------------------------------------------ */

/** POST /v1/auth/dev-login — local dev only (404 in prod). */
export function useDevLogin() {
  return useMutation({
    mutationFn: (email: string) => api.post<AuthResponse>('/auth/dev-login', { email }),
  });
}

/** POST /v1/leads/{id}/confirm (Q1–Q6). 422 -> ApiError.fields keyed by request field. */
export function useConfirmLead(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ConfirmPayload) =>
      api.post<LeadDetail>(`/leads/${leadId}/confirm`, payload),
    onSuccess: (detail) => {
      qc.setQueryData(queryKeys.lead(leadId), detail);
      qc.invalidateQueries({ queryKey: ['leads'] });
      qc.invalidateQueries({ queryKey: queryKeys.metrics });
      qc.invalidateQueries({ queryKey: ['matches', leadId] });
      qc.invalidateQueries({ queryKey: ['reminders'] });
    },
  });
}

/** PATCH /v1/leads/{id}/source-data — admin only (403 otherwise). */
export function usePatchSourceData(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<SourceData>) =>
      api.patch<LeadDetail>(`/leads/${leadId}/source-data`, payload),
    onSuccess: (detail) => {
      qc.setQueryData(queryKeys.lead(leadId), detail);
      qc.invalidateQueries({ queryKey: ['leads'] });
      qc.invalidateQueries({ queryKey: ['matches', leadId] });
    },
  });
}

/** POST /v1/leads/{id}/stage — remark required (422 otherwise). */
export function useStageChange(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: StageChangePayload) =>
      api.post<LeadDetail>(`/leads/${leadId}/stage`, payload),
    onSuccess: (detail) => {
      qc.setQueryData(queryKeys.lead(leadId), detail);
      qc.invalidateQueries({ queryKey: ['leads'] });
      qc.invalidateQueries({ queryKey: queryKeys.metrics });
      qc.invalidateQueries({ queryKey: ['reminders'] });
    },
  });
}

/** POST /v1/leads/{id}/hot {is_hot}. */
export function useToggleHot(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (isHot: boolean) => api.post<LeadRow>(`/leads/${leadId}/hot`, { is_hot: isHot }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.lead(leadId) });
      qc.invalidateQueries({ queryKey: ['leads'] });
      qc.invalidateQueries({ queryKey: queryKeys.metrics });
      qc.invalidateQueries({ queryKey: queryKeys.buckets });
    },
  });
}

/** POST /v1/leads/ingest — Add New Lead. */
export function useIngestLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: IngestPayload) => api.post<LeadRow>('/leads/ingest', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['leads'] });
      qc.invalidateQueries({ queryKey: queryKeys.metrics });
    },
  });
}

/** POST /v1/reminders. */
export function useCreateReminder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReminderCreatePayload) => api.post<Reminder>('/reminders', payload),
    onSuccess: (reminder) => {
      qc.invalidateQueries({ queryKey: ['reminders'] });
      qc.invalidateQueries({ queryKey: queryKeys.metrics });
      qc.invalidateQueries({ queryKey: queryKeys.lead(reminder.lead_id) });
    },
  });
}

/** PATCH /v1/reminders/{id} — variables carry the reminder id. */
export function useUpdateReminder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, done }: { id: string; done?: boolean }) =>
      api.patch<Reminder>(`/reminders/${id}`, { done }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reminders'] });
      qc.invalidateQueries({ queryKey: queryKeys.metrics });
    },
  });
}

/** POST /v1/leads/{id}/visits — sets stage visit_scheduled + auto +2h reminder. */
export function useCreateVisit(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: VisitCreatePayload) =>
      api.post<VisitCreateResponse>(`/leads/${leadId}/visits`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.lead(leadId) });
      qc.invalidateQueries({ queryKey: ['leads'] });
      qc.invalidateQueries({ queryKey: ['reminders'] });
      qc.invalidateQueries({ queryKey: queryKeys.metrics });
    },
  });
}

/** POST /v1/supply/{id}/interest — "I have a buyer". */
export function useAddInterest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note, lead_id }: { id: string; note?: string; lead_id?: string }) =>
      api.post<InterestResponse>(`/supply/${id}/interest`, { note, lead_id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.supply });
      qc.invalidateQueries({ queryKey: queryKeys.societyInsights });
    },
  });
}

/** POST /v1/buckets/rematch. */
export function useRematch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<RematchResponse>('/buckets/rematch'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.buckets });
    },
  });
}

/** POST /v1/buckets/{id}/broadcast {mode}. */
export function useBroadcast() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, mode }: { id: string; mode: BroadcastMode }) =>
      api.post<BroadcastResponse>(`/buckets/${id}/broadcast`, { mode }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.buckets });
    },
  });
}

/** POST /v1/societies/insights. */
export function useAddInsight() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: InsightCreatePayload) =>
      api.post<SocietyInsight>('/societies/insights', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.societyInsights });
    },
  });
}

/** PATCH /v1/settings/integrations {key, enabled} — admin. */
export function useUpdateIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      api.patch<SettingsResponse>('/settings/integrations', { key, enabled }),
    onSuccess: (settings) => {
      qc.setQueryData(queryKeys.settings, settings);
    },
  });
}

/** PATCH /v1/settings/assignment {method} — admin. */
export function useUpdateAssignment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ method }: { method: string }) =>
      api.patch<SettingsResponse>('/settings/assignment', { method }),
    onSuccess: (settings) => {
      qc.setQueryData(queryKeys.settings, settings);
    },
  });
}
