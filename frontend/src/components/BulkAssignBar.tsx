/* Floating action bar shown when leads are selected — bulk reassign / unassign. */
import { useState } from "react";
import { useAssignees, useBulkAssign } from "../lib/queries";
import { useToast } from "./Toast";

export function BulkAssignBar({ ids, onDone }: { ids: string[]; onDone: () => void }) {
  const { data } = useAssignees();
  const bulk = useBulkAssign();
  const toast = useToast();
  const [pick, setPick] = useState("");

  if (ids.length === 0) return null;

  const apply = (assigned_to: string | null) => {
    bulk.mutate({ ids, assigned_to }, {
      onSuccess: (r) => { toast(`${r.updated} leads ${assigned_to ? "→ " + assigned_to : "unassigned"}`, "green", "✓"); onDone(); },
      onError: (e: any) => toast(e.message, "gold", "⚠"),
    });
  };

  return (
    <div style={{
      position: "sticky", top: 0, zIndex: 20, display: "flex", alignItems: "center", gap: 12,
      background: "var(--ink)", color: "#fff", padding: "10px 16px", borderRadius: 11,
      boxShadow: "var(--shadow-lg)", marginBottom: 12,
    }}>
      <b style={{ fontSize: 13.5 }}>{ids.length} selected</b>
      <div style={{ flex: 1 }} />
      <select
        value={pick}
        disabled={bulk.isPending}
        onChange={(e) => { const v = e.target.value; setPick(""); if (v) apply(v); }}
        style={{ border: 0, borderRadius: 8, padding: "7px 10px", fontSize: 12.5, fontWeight: 600, background: "#fff", color: "var(--ink)" }}
      >
        <option value="">Reassign to…</option>
        {(data?.items ?? []).map((a) => <option key={a.email} value={a.name}>{a.name}</option>)}
      </select>
      <button className="btn sm" style={{ background: "rgba(255,255,255,.16)", color: "#fff" }}
        disabled={bulk.isPending} onClick={() => apply(null)}>Unassign</button>
      <button className="btn sm" style={{ background: "rgba(255,255,255,.16)", color: "#fff" }} onClick={onDone}>Clear</button>
    </div>
  );
}
