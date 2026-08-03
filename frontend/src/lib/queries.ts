import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ConfirmPayload, MatchPreviewReq } from "./api";
import { LEAD_SEGMENTS } from "./leads";

export function useInventory() {
  return useQuery({ queryKey: ["inventory"], queryFn: api.inventory, staleTime: 60_000 });
}

/* Polls — the webhook has no push channel to the browser, so an interval is the
   whole sync mechanism. 5s on the conversation, since someone is watching it. */
export function useWaMessages(phone?: string) {
  return useQuery({
    queryKey: ["wa-messages", phone ?? "all"],
    queryFn: () => api.waMessages(phone),
    refetchInterval: 5_000,
  });
}

export function useSendWa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ phone, text }: { phone: string; text: string }) => api.waSend(phone, text),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wa-messages"] }),
  });
}

/* Topbar unread dot. One MAX() server-side, so a 30s poll from every page is fine —
   unlike useWaMessages, which pulls the whole conversation set. */
export function useWaLatest(enabled: boolean) {
  return useQuery({
    queryKey: ["wa-latest"],
    queryFn: api.waLatest,
    enabled,
    refetchInterval: 30_000,
  });
}

/* master_societies is cached server-side and rarely changes — no need to refetch. */
export function useSocietiesByCity(city: string) {
  return useQuery({
    queryKey: ["societies-by-city", city],
    queryFn: () => api.societiesByCity(city),
    enabled: !!city,
    staleTime: Infinity,
  });
}

export function useAssignWaContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ phone, assigned_to }: { phone: string; assigned_to: string | null }) =>
      api.waAssign(phone, assigned_to),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wa-messages"] }),
  });
}

export function useBackfillWaAssign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.waBackfillAssign,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wa-messages"] }),
  });
}

export function useMarkWaContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ phone, tag }: { phone: string; tag: import("./api").WaTag }) =>
      api.waMark(phone, tag),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wa-messages"] }),
  });
}

export function useCreateWaLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.waCreateLead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wa-messages"] });  // the thread now has a lead
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["lead-counts"] });
    },
  });
}

export function useGupshupRecent() {
  return useQuery({ queryKey: ["gupshup-recent"], queryFn: api.gupshupRecent, refetchInterval: 10_000 });
}

export function useSupply() {
  return useQuery({ queryKey: ["supply"], queryFn: api.supply, staleTime: 60_000 });
}

export function useLeads(segment: string) {
  return useQuery({ queryKey: ["leads", segment], queryFn: () => api.leads(segment), staleTime: 60_000 });
}

export function useLeadCounts() {
  return useQuery({ queryKey: ["lead-counts"], queryFn: api.leadCounts, staleTime: 60_000 });
}

/* Fetch every segment at once (parallel, cached under the same ["leads", seg]
   keys the per-tab pages use) and return a flat list tagged with each lead's
   segment. Only fires while `enabled` — i.e. when the global search is active. */
export function useAllLeads(enabled: boolean) {
  const results = useQueries({
    queries: LEAD_SEGMENTS.map((s) => ({
      queryKey: ["leads", s.seg],
      queryFn: () => api.leads(s.seg),
      staleTime: 60_000,
      enabled,
    })),
  });
  const leads = results.flatMap((r, i) =>
    (r.data?.items ?? []).map((lead) => ({ lead, segment: LEAD_SEGMENTS[i] })),
  );
  return { leads, isLoading: enabled && results.some((r) => r.isLoading) };
}

export function useLead(id: string) {
  return useQuery({ queryKey: ["lead", id], queryFn: () => api.lead(id), staleTime: 30_000 });
}

export function useLeadMatches(id: string) {
  return useQuery({ queryKey: ["lead-matches", id], queryFn: () => api.leadMatches(id), staleTime: 60_000 });
}

export function useLatestVisit(id: string) {
  return useQuery({ queryKey: ["visit", id], queryFn: () => api.latestVisit(id), staleTime: 30_000 });
}

export function useBookingConfig() {
  return useQuery({ queryKey: ["booking-config"], queryFn: api.bookingConfig, staleTime: 5 * 60_000 });
}

export function useMarkPriority(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uid, priority }: { uid: string; priority: boolean }) => api.markPriority(uid, priority),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead-matches", leadId] });
      qc.invalidateQueries({ queryKey: ["match-preview"] });
      qc.invalidateQueries({ queryKey: ["supply"] });
    },
  });
}

/** Live matching from in-progress form fields. Keyed on the requirement so
    react-query caches identical requirements; keepPreviousData avoids flicker. */
export function useMatchPreview(req: MatchPreviewReq) {
  return useQuery({
    queryKey: ["match-preview", req],
    queryFn: () => api.matchPreview(req),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export function useLeadNotes(id: string, enabled = true) {
  return useQuery({
    queryKey: ["lead-notes", id],
    queryFn: () => api.leadNotes(id),
    enabled: enabled && !!id,
    staleTime: 15_000,
  });
}
export function useAddNote(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => api.addNote(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lead-notes", id] }),
  });
}
export function usePatchSourceData(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Parameters<typeof api.patchSourceData>[1]) => api.patchSourceData(id, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["lead-matches", id] });
    },
  });
}

/* Click-to-call: rings the caller's own phone, then bridges to the lead. */
export function usePlaceCall() {
  return useMutation({ mutationFn: (leadId: string) => api.placeCall(leadId) });
}

export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: api.users });
}

export function useLogs(params: import("./api").LogsParams) {
  return useQuery({
    queryKey: ["logs", params],
    queryFn: () => api.logs(params),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}
export function useLogActors() {
  return useQuery({ queryKey: ["log-actors"], queryFn: api.logActors, staleTime: 60_000 });
}

export function useAssignees() {
  return useQuery({ queryKey: ["assignees"], queryFn: api.assignees, staleTime: 60_000 });
}
export function useAssignLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, assigned_to }: { id: string; assigned_to: string | null }) => api.assignLead(id, assigned_to),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["lead"] });
    },
  });
}
export function useBulkAssign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, assigned_to }: { ids: string[]; assigned_to: string | null }) => api.bulkAssign(ids, assigned_to),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
export function useUserMutations() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: ["users"] });
  // reassigning changes lead ownership too, so refresh leads + dashboard as well
  const invAll = () => { inv(); qc.invalidateQueries({ queryKey: ["leads"] }); };
  return {
    create: useMutation({ mutationFn: api.createUser, onSuccess: inv }),
    update: useMutation({ mutationFn: ({ id, patch }: { id: string; patch: any }) => api.updateUser(id, patch), onSuccess: inv }),
    remove: useMutation({ mutationFn: api.deleteUser, onSuccess: inv }),
    reassign: useMutation({ mutationFn: ({ id, toUserId }: { id: string; toUserId: string }) => api.reassignUserLeads(id, toUserId), onSuccess: invAll }),
  };
}

export function useConfirmLead(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ConfirmPayload) => api.confirmLead(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

export function useRejectLead(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ reason, notes }: { reason: string; notes: string }) => api.rejectLead(id, reason, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

/** Log a call attempt (Yes/No) from the New Leads / Follow-up worklist. */
export function useCallResult() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, connected, reason, notes }:
      { id: string; connected: boolean; reason?: string; notes?: string }) =>
      api.callResult(id, connected, reason, notes),
    onSuccess: (_d, { id }) => {
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["lead-notes", id] });  // a "No" writes a note
    },
  });
}

/** All visits booked for a lead — fetched only when the row is expanded. */
export function useLeadCrmVisits(id: string, enabled = true) {
  return useQuery({
    queryKey: ["crm-visits", id],
    queryFn: () => api.leadCrmVisits(id),
    enabled: enabled && !!id,
    staleTime: 30_000,
  });
}

/** Star / un-star a lead as hot (optimistic — the star flips instantly). */
export function useMarkHot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, hot }: { id: string; hot: boolean }) => api.markHot(id, hot),
    onSuccess: (_d, { id }) => {
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["lead", id] });
    },
  });
}

/** Set a manual follow-up (from the lead detail, after a connected call). */
export function useSetFollowup(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (followUpAt: string) => api.setFollowup(id, followUpAt),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

export function useSyncInventory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.syncInventory,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory"] }),
  });
}

/** Pull new leads from the Google Sheets now (same job the 11:30/14:00 cron runs).
    Insert-only + idempotent, so re-running is safe. Admin-triggered from New Leads. */
export function useSyncLeads() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.syncLeads,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

/* ── Auto-dialer ─────────────────────────────────────────────────────────── */

export function useDialerFields() {
  return useQuery({ queryKey: ["dialer-fields"], queryFn: api.dialerFields, staleTime: 300_000 });
}

/** Live match count. Debounced by the caller — this fires on every rule edit. */
export function useRulePreview(rules: import("./api").RuleNode) {
  return useQuery({
    queryKey: ["dialer-preview", rules],
    queryFn: () => api.dialerPreview(rules),
    placeholderData: keepPreviousData,
  });
}

export function useCampaigns() {
  return useQuery({ queryKey: ["campaigns"], queryFn: api.campaigns, refetchInterval: 5_000 });
}

/* The dial loop lives on the server; 2s polling is how the browser learns a call
   started or ended. Only polls while a campaign is actually selected. */
export function useCampaign(id: string | null) {
  return useQuery({
    queryKey: ["campaign", id],
    queryFn: () => api.campaign(id as string),
    enabled: !!id,
    refetchInterval: 2_000,
  });
}

export function useCreateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createCampaign,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

export function useCampaignAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: "start" | "pause" | "stop" }) =>
      api.campaignAction(id, action),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["campaign"] });
    },
  });
}

/** "86.5 L" / 132 lacs → display string like the prototype's ₹ pricing */
export function formatPrice(priceLacs: number | null, priceText: string | null): string {
  if (priceLacs != null) {
    if (priceLacs >= 100) {
      const cr = priceLacs / 100;
      return `₹${Number.isInteger(cr) ? cr : cr.toFixed(2).replace(/0+$/, "").replace(/\.$/, "")} Cr`;
    }
    return `₹${priceLacs} Lakh`;
  }
  return priceText || "—";
}
