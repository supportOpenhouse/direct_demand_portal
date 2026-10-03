/* Action bar for the lead worklists — bulk reassign / unassign, plus the
   "select first N" shortcuts. Appears only once at least one row is ticked. */
import { useState } from "react";
import { useAssignees, useBulkAssign } from "../lib/queries";
import { ALL_STAGES, stageLabel } from "../lib/leads";
import { useToast } from "./Toast";

/* Stages the bulk bar can move leads to, as `stage` or `stage:warmth`. Visit stages are
   left out — only a booking sets them (the server 422s) — and Qualified is three
   options because the server refuses it without Hot / Warm / Cold. */
const STAGE_OPTIONS = ALL_STAGES
  .filter((st) => st !== "visit_scheduled" && st !== "revisit_scheduled")
  .flatMap((st) => st === "qualified"
    ? ["hot", "warm", "cold"].map((q) => ({ v: `qualified:${q}`, label: `${stageLabel(st)} · ${q[0].toUpperCase()}${q.slice(1)}` }))
    : [{ v: st as string, label: stageLabel(st) }]);

export function BulkAssignBar(
  { ids, onDone, total, onSelectAll }: {
    ids: string[];
    onDone: () => void;
    total: number;                       // rows currently on screen, after filters
    onSelectAll: () => void;             // every filtered row, across all pages
  },
) {
  const { data } = useAssignees();
  const bulk = useBulkAssign();
  const toast = useToast();
  const [pick, setPick] = useState("");
  const [stagePick, setStagePick] = useState("");   // "" = each lead keeps its own stage

  if (ids.length === 0) return null;

  const apply = (assigned_to: string | null) => {
    const [stage, qualified_status] = stagePick ? stagePick.split(":") : [];
    bulk.mutate({ ids, assigned_to, stage, qualified_status }, {
      onSuccess: (r) => {
        toast(`${r.updated} leads ${assigned_to ? "→ " + assigned_to : "unassigned"}`
          + (r.stage ? ` · ${STAGE_OPTIONS.find((o) => o.v === stagePick)?.label}` : ""), "green");
        setStagePick("");
        onDone();
      },
      onError: (e: any) => toast(e.message, "gold"),
    });
  };

  return (
    <div style={{
      position: "sticky", top: 0, zIndex: 20, display: "flex", alignItems: "center", gap: 12,
      background: "var(--brand)", color: "var(--on-brand)", padding: "10px 16px", borderRadius: 11,
      boxShadow: "var(--shadow-lg)", marginBottom: 12,
    }}>
      <b style={{ fontSize: 13.5 }}>{ids.length} selected</b>
      <span style={{ fontSize: 11.5, opacity: .62 }}>of {total}</span>
      {ids.length < total && (
        <button className="btn sm" style={{ background: "var(--on-accent-2)", color: "var(--on-accent)" }}
          onClick={onSelectAll}>Select all</button>
      )}
      <div style={{ flex: 1 }} />
      {/* a setting, not an action: it rides along with Reassign / Unassign below */}
      <select
        value={stagePick}
        disabled={bulk.isPending}
        onChange={(e) => setStagePick(e.target.value)}
        title="Stage to move the selected leads to when they are reassigned"
        style={{ border: 0, borderRadius: 8, padding: "7px 10px", fontSize: 12.5, fontWeight: 600, background: "var(--panel)", color: "var(--ink)" }}
      >
        <option value="">Keep current stage</option>
        {STAGE_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
      </select>
      <select
        value={pick}
        disabled={bulk.isPending}
        onChange={(e) => { const v = e.target.value; setPick(""); if (v) apply(v); }}
        style={{ border: 0, borderRadius: 8, padding: "7px 10px", fontSize: 12.5, fontWeight: 600, background: "var(--panel)", color: "var(--ink)" }}
      >
        <option value="">Reassign to…</option>
        {(data?.items ?? []).map((a) => <option key={a.email} value={a.name}>{a.name}</option>)}
      </select>
      <button className="btn sm" style={{ background: "var(--on-accent-2)", color: "var(--on-accent)" }}
        disabled={bulk.isPending} onClick={() => apply(null)}>Unassign</button>
      <button className="btn sm" style={{ background: "var(--on-accent-2)", color: "var(--on-accent)" }}
        onClick={onDone}>Clear</button>
    </div>
  );
}
