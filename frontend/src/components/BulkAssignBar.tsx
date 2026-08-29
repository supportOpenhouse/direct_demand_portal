/* Action bar for the lead worklists — bulk reassign / unassign, plus the
   "select first N" shortcuts.

   Shown at zero selected, not only once something is ticked. The shortcuts live in
   here, so a bar that appears only after you've already selected something could
   never offer the fast way to select. The destructive half is disabled instead of
   hidden: the row stays put rather than shifting the table down under the cursor the
   moment a checkbox is clicked. */
import { useState } from "react";
import { useAssignees, useBulkAssign } from "../lib/queries";
import { SelectFirst } from "./SelectFirst";
import { useToast } from "./Toast";

export function BulkAssignBar(
  { ids, onDone, total, onSelectFirst }: {
    ids: string[];
    onDone: () => void;
    total: number;                       // rows currently on screen, after filters
    onSelectFirst: (n: number) => void;
  },
) {
  const { data } = useAssignees();
  const bulk = useBulkAssign();
  const toast = useToast();
  const [pick, setPick] = useState("");
  const none = ids.length === 0;

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
      <span style={{ fontSize: 11.5, opacity: .62 }}>of {total}</span>
      <SelectFirst total={total} onPick={onSelectFirst} btnClass="btn sm"
        style={{ background: "rgba(255,255,255,.16)", color: "#fff" }} />
      <div style={{ flex: 1 }} />
      <select
        value={pick}
        disabled={bulk.isPending || none}
        onChange={(e) => { const v = e.target.value; setPick(""); if (v) apply(v); }}
        style={{ border: 0, borderRadius: 8, padding: "7px 10px", fontSize: 12.5, fontWeight: 600, background: "#fff", color: "var(--ink)" }}
      >
        <option value="">Reassign to…</option>
        {(data?.items ?? []).map((a) => <option key={a.email} value={a.name}>{a.name}</option>)}
      </select>
      <button className="btn sm" style={{ background: "rgba(255,255,255,.16)", color: "#fff" }}
        disabled={bulk.isPending || none} onClick={() => apply(null)}>Unassign</button>
      <button className="btn sm" style={{ background: "rgba(255,255,255,.16)", color: "#fff" }}
        disabled={none} onClick={onDone}>Clear</button>
    </div>
  );
}
