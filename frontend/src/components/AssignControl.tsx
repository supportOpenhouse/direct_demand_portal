/* Assign / reassign a lead to a user, from the frontend. Unassigned leads show an
   "Assign ▾" button; assigned ones show the name with a tweak option. */
import { useState, useRef, useEffect } from "react";
import { useAssignees, useAssignLead } from "../lib/queries";
import { useToast } from "./Toast";

export function AssignControl({ leadId, assignedTo, compact }: { leadId: string; assignedTo: string | null; compact?: boolean }) {
  const { data } = useAssignees();
  const assign = useAssignLead();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("click", onDoc);
    return () => document.removeEventListener("click", onDoc);
  }, []);

  const pick = (name: string | null) => {
    setOpen(false);
    assign.mutate({ id: leadId, assigned_to: name }, {
      onSuccess: () => toast(name ? `Assigned to ${name}` : "Unassigned", "green", "✓"),
      onError: (e: any) => toast(e.message, "gold", "⚠"),
    });
  };

  const people = data?.items ?? [];

  return (
    <div className="ms" ref={box} style={{ position: "relative", display: "inline-block" }}>
      {assignedTo ? (
        <span
          onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
          style={{ fontSize: 12.5, cursor: "pointer", borderBottom: "1px dashed var(--line)" }}
          title="Reassign"
        >
          {assignedTo}
        </span>
      ) : (
        <button
          className="btn sm"
          style={{ background: "var(--blue-soft)", color: "var(--blue)", padding: "4px 10px", fontSize: 11.5 }}
          onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        >
          + Assign
        </button>
      )}
      {open && (
        <div className="ms-panel" style={{ display: "block", right: compact ? 0 : "auto", minWidth: 160 }} onClick={(e) => e.stopPropagation()}>
          {people.length === 0 && <div className="ms-opt" style={{ color: "var(--muted)" }}>No users yet — add in Settings</div>}
          {people.map((p) => (
            <label key={p.email} className="ms-opt" onClick={() => pick(p.name)}>{p.name}</label>
          ))}
          {assignedTo && (
            <label className="ms-opt" style={{ color: "var(--coral)", borderTop: "1px solid var(--line-2)" }} onClick={() => pick(null)}>
              Unassign
            </label>
          )}
        </div>
      )}
    </div>
  );
}
