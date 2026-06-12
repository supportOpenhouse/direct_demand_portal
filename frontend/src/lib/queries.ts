import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export function useInventory() {
  return useQuery({ queryKey: ["inventory"], queryFn: api.inventory, staleTime: 60_000 });
}

export function useSupply() {
  return useQuery({ queryKey: ["supply"], queryFn: api.supply, staleTime: 60_000 });
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
