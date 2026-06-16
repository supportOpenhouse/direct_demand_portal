import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ConfirmPayload, MatchPreviewReq } from "./api";

export function useInventory() {
  return useQuery({ queryKey: ["inventory"], queryFn: api.inventory, staleTime: 60_000 });
}

export function useSupply() {
  return useQuery({ queryKey: ["supply"], queryFn: api.supply, staleTime: 60_000 });
}

export function useLeads(segment: string) {
  return useQuery({ queryKey: ["leads", segment], queryFn: () => api.leads(segment), staleTime: 60_000 });
}

export function useDashboard() {
  return useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, staleTime: 60_000 });
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

export function useLeadNotes(id: string) {
  return useQuery({ queryKey: ["lead-notes", id], queryFn: () => api.leadNotes(id), staleTime: 15_000 });
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

export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: api.users });
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
export function useUserMutations() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: ["users"] });
  return {
    create: useMutation({ mutationFn: api.createUser, onSuccess: inv }),
    update: useMutation({ mutationFn: ({ id, patch }: { id: string; patch: any }) => api.updateUser(id, patch), onSuccess: inv }),
    remove: useMutation({ mutationFn: api.deleteUser, onSuccess: inv }),
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

export function useSyncInventory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.syncInventory,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory"] }),
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
