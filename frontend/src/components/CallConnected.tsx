/* "Call connected?" gate for the New Leads / Follow-up worklists.
   The lead row is NOT clickable — Yes is the only way in:
     Yes → logs a connected call (resets the miss streak) and opens the lead.
     No  → asks WHY (reason + mandatory notes). The reason decides the outcome:
           didn't pick → +3h, switched off → +6h (both clamped to 10:00–19:00 IST
           calling hours by the backend), invalid number → Rejected.
           10 misses on a never-reached lead still escalates to RNR. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCallResult } from "../lib/queries";
import { useToast } from "./Toast";

const MISS_REASONS = [
  { value: "Did Not Pick / Not Reachable", hint: "Call back in 3 hours" },
  { value: "Switched Off", hint: "Call back in 6 hours" },
  { value: "Invalid Number", hint: "Moves the lead to Rejected" },
];

/** Local time of an ISO instant, e.g. "Tue 10:00 AM" — used to confirm when the
    auto follow-up actually landed (it may have been pushed to the next morning). */
const whenLabel = (iso?: string | null) =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        weekday: "short", hour: "numeric", minute: "2-digit",
      })
    : null;

function MissReasonModal({ leadId, onClose }: { leadId: string; onClose: () => void }) {
  const m = useCallResult();
  const toast = useToast();
  const [reason, setReason] = useState(MISS_REASONS[0].value);
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState(false);
  const hint = MISS_REASONS.find((r) => r.value === reason)?.hint;

  const submit = () => {
    if (!reason || !notes.trim()) { setErr(true); return; }
    m.mutate(
      { id: leadId, connected: false, reason, notes: notes.trim() },
      {
        onSuccess: (d) => {
          if (d.rejected) toast("Invalid number — moved to Rejected", "blue", "✕");
          else if (d.moved_to_rnr) toast("10 missed calls — moved to RNR", "gold", "✕");
          else {
            const at = whenLabel(d.follow_up_at);
            toast(at ? `Not reached · follow-up ${at}` : "Not reached · follow-up set", "gold", "↻");
          }
          onClose();
        },
        onError: (e: any) => toast(e.message, "gold", "⚠"),
      },
    );
  };

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="mh"><h3>Why didn't the call connect?</h3><div className="icon-btn" onClick={onClose}>✕</div></div>
        <div className="mb">
          <div className="field">
            <label>Reason <span className="req">*</span></label>
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              {MISS_REASONS.map((r) => <option key={r.value} value={r.value}>{r.value}</option>)}
            </select>
            {hint && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 5 }}>→ {hint}</div>}
          </div>
          <div className={"field" + (err && !notes.trim() ? " invalid" : "")} style={{ marginBottom: 0 }}>
            <label>Notes <span className="req">*</span></label>
            <textarea rows={3} value={notes} autoFocus placeholder="What happened on this attempt?"
              onChange={(e) => setNotes(e.target.value)} />
          </div>
          {err && !notes.trim() && <div className="mand-flag show">⚠ Notes are required.</div>}
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" style={{ background: "var(--coral)", color: "#fff" }}
            onClick={submit} disabled={m.isPending}>
            {m.isPending ? "Saving…" : "Log attempt"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function CallConnected({ leadId }: { leadId: string }) {
  const nav = useNavigate();
  const m = useCallResult();
  const [asking, setAsking] = useState(false);

  const yes = (e: React.MouseEvent) => {
    e.stopPropagation();
    m.mutate({ id: leadId, connected: true }, { onSuccess: () => nav(`/leads/${leadId}`) });
  };

  return (
    <div className="cc" onClick={(e) => e.stopPropagation()}>
      <span className="cc-q">Connected?</span>
      <button className="cc-btn yes" disabled={m.isPending} onClick={yes}>Yes</button>
      <button className="cc-btn no" onClick={(e) => { e.stopPropagation(); setAsking(true); }}>No</button>
      {asking && <MissReasonModal leadId={leadId} onClose={() => setAsking(false)} />}
    </div>
  );
}
