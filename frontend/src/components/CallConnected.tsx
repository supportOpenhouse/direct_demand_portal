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

// hours until the callback; null = the number is unusable, so the lead is rejected
const MISS_REASONS: { value: string; hours: number | null }[] = [
  { value: "Did Not Pick / Not Reachable", hours: 3 },
  { value: "Switched Off", hours: 6 },
  { value: "Invalid Number", hours: null },
];

const IST_MIN = 330;              // Asia/Kolkata is UTC+5:30 year-round (no DST)
const WORK_START = 10, WORK_END = 19;

/** Preview of the follow-up the backend will set. Mirrors _within_calling_hours()
    in backend/app/routers/leads.py — the backend stays authoritative (its response
    carries the real time); this only shows the RM what to expect before they save. */
function previewFollowup(hours: number): { at: Date; rolled: boolean } {
  const due = new Date(Date.now() + hours * 3600_000);
  // shift so the getUTC* accessors read IST wall-clock, matching the backend's compare
  const ist = new Date(due.getTime() + IST_MIN * 60_000);
  const hour = ist.getUTCHours();
  let rolled = false;
  if (hour < WORK_START) {
    ist.setUTCHours(WORK_START, 0, 0, 0);
    rolled = true;
  } else if (hour >= WORK_END) {
    ist.setUTCDate(ist.getUTCDate() + 1);
    ist.setUTCHours(WORK_START, 0, 0, 0);
    rolled = true;
  }
  return { at: new Date(ist.getTime() - IST_MIN * 60_000), rolled };
}

const istLabel = (d: Date) =>
  d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short",
    hour: "numeric", minute: "2-digit",
  });

function MissReasonModal({ leadId, onClose }: { leadId: string; onClose: () => void }) {
  const m = useCallResult();
  const toast = useToast();
  const [reason, setReason] = useState(MISS_REASONS[0].value);
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState(false);
  const hours = MISS_REASONS.find((r) => r.value === reason)?.hours ?? null;
  const preview = hours != null ? previewFollowup(hours) : null;

  const submit = () => {
    if (!reason || !notes.trim()) { setErr(true); return; }
    m.mutate(
      { id: leadId, connected: false, reason, notes: notes.trim() },
      {
        onSuccess: (d) => {
          if (d.rejected) toast("Invalid number — moved to Rejected", "blue", "✕");
          else if (d.moved_to_rnr) toast("10 missed calls — moved to RNR", "gold", "✕");
          else {
            const at = d.follow_up_at ? istLabel(new Date(d.follow_up_at)) : null;
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
          </div>
          <div className={"field" + (err && !notes.trim() ? " invalid" : "")} style={{ marginBottom: 0 }}>
            <label>Notes <span className="req">*</span></label>
            <textarea rows={3} value={notes} autoFocus placeholder="What happened on this attempt?"
              onChange={(e) => setNotes(e.target.value)} />
          </div>
          {err && !notes.trim() && <div className="mand-flag show">⚠ Notes are required.</div>}

          {/* what saving will actually do — the +3h/+6h landing time, already
              clamped to calling hours, or the terminal outcome */}
          <div className="cc-outcome">
            {preview ? (
              <>
                <span className="cco-lbl">Follow-up will be set for</span>
                <b className="cco-at">{istLabel(preview.at)}</b>
                {preview.rolled && (
                  <span className="cco-why">+{hours}h lands outside calling hours → next morning</span>
                )}
              </>
            ) : (
              <span className="cco-lbl">This lead will move to <b style={{ color: "var(--coral)" }}>Rejected</b> — no follow-up.</span>
            )}
          </div>
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
