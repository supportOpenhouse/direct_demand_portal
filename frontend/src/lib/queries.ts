import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ConfirmPayload, MatchPreviewReq } from "./api";
import { LEAD_SEGMENTS } from "./leads";

/* Org-wide settings.

   Read by every lead table to decide whether to render phone numbers. 30s stale, so
   another user's open tab picks up a policy change when they next focus it (react-
   query refetches stale queries on window focus) rather than only on a hard reload —
   without paying a request per navigation forever. */
export function useAppSettings() {
  return useQuery({
    queryKey: ["app-settings"],
    queryFn: api.appSettings,
    staleTime: 30_000,
    // Keep the last known value while refetching: a hide-flag that flickers off
    // mid-refetch would flash the numbers it exists to conceal.
    placeholderData: keepPreviousData,
  });
}

export function useSetAppSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: "hide_lead_phones"; value: boolean }) =>
      api.setAppSetting(key, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["app-settings"] }),
  });
}

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

export function useBulkCreateWaLeads() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (phones: string[]) => api.waBulkCreateLeads(phones),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wa-messages"] });  // rows become lead-tagged
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

/* Local switcher only — see api.devUserList for why it bypasses the dev header. */
export function useDevUserList(enabled: boolean) {
  // finite staleTime + retries: the API is often still booting when the page first
  // loads locally, and a permanently-cached failure is the whole bug this replaces
  return useQuery({
    queryKey: ["dev-user-list"], queryFn: api.devUserList, enabled,
    staleTime: 30_000, retry: 3, retryDelay: 1_000, refetchOnWindowFocus: true,
  });
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
/* mm:ss between two call timestamps, "—" when either end is missing. */
export function callDuration(startAt: string | null, endAt: string | null): string {
  if (!startAt || !endAt) return "—";
  const secs = Math.round((+new Date(endAt) - +new Date(startAt)) / 1000);
  if (secs < 0) return "—";
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}

export function useLeadCalls(id: string, enabled = true) {
  return useQuery({
    queryKey: ["lead-calls", id],
    queryFn: () => api.leadCalls(id),
    enabled: enabled && !!id,
    staleTime: 15_000,
  });
}

/* `enabled` matters for the campaign-scoped view: without it, the first render
   (before a campaign is picked) fires an *unscoped* request that pulls every call
   in the system just to throw it away. */
export function useCallLog(params: import("./api").CallLogParams, enabled = true) {
  return useQuery({
    queryKey: ["call-log", params],
    queryFn: () => api.callLog(params),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}
export function useCallLogActors() {
  return useQuery({ queryKey: ["call-log-actors"], queryFn: api.callLogActors, staleTime: 60_000 });
}
export function useSyncCallLog() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ from, to }: { from: string; to: string }) => api.syncCallLog(from, to),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["call-log"] }),
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
    mutationFn: ({ id, connected, reason, notes, queueItemId }:
      { id: string; connected: boolean; reason?: string; notes?: string;
        queueItemId?: string }) =>
      api.callResult(id, connected, reason, notes, queueItemId),
    onSuccess: (_d, { id }) => {
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["lead-notes", id] });  // a "No" writes a note
      qc.invalidateQueries({ queryKey: ["my-calls"] });        // clears "needs result"
    },
  });
}

/* Live Calls.

   The SSE stream carries only a nudge; this query is what actually builds the page,
   so live and fallback share one code path. When the stream is healthy we don't poll
   at all; when it isn't — no Redis across a split scheduler process, a dropped
   connection — this drops to a 4s interval and the page degrades to a few seconds of
   latency rather than to nothing. */
export function useMyCalls(streamHealthy: boolean, enabled = true) {
  return useQuery({
    queryKey: ["my-calls"],
    queryFn: api.myCalls,
    // Off for non-RMs. The Topbar button has to call this hook unconditionally (hook
    // order can't be conditional), so without this every admin would still run three
    // Neon queries on every page for a button they never see.
    enabled,
    refetchInterval: streamHealthy ? false : 4_000,
    // The sidebar badge mounts this on every page for every user, admins included.
    // Without a staleTime each tab focus re-runs three Neon queries from Singapore
    // for people who never dial; the page's own polling is unaffected because an
    // explicit refetchInterval overrides staleness.
    staleTime: 15_000,
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

/** Live match count. Debounced by the caller — this fires on every rule edit.
    Strategy and pool are part of it: under 'assigned' the count is what those RMs own. */
export function useRulePreview(rules: import("./api").RuleNode, strategy: string, rms: string[]) {
  return useQuery({
    queryKey: ["dialer-preview", rules, strategy, rms],
    queryFn: () => api.dialerPreview(rules, strategy, rms),
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
    // Only a running campaign changes under you. Paused/done/draft are static, so
    // Previous Campaigns doesn't re-poll finished history 30 times a minute.
    refetchInterval: (q) => (q.state.data?.campaign.status === "running" ? 2_000 : false),
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
