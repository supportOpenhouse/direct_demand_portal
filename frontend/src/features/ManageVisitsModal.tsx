/* Manage visits — every Openhouse visit this lead has, and the four things you can do
   to one.

   This replaced the old "Book Revisit" button, which could only ever do one thing and
   had no way to see what was already booked. The list shows EVERY visit including
   completed and cancelled ones: the history is the point, since a revisit is defined
   against it.

   ⚠️ A REVISIT is the same buyer returning to the SAME property — not simply a lead with
   more than one visit. So "Schedule revisit" lives on a completed visit ROW (it clones
   that visit's property, via Core's revisit-visits endpoint, which copies the buyer,
   home, broker and sales manager and mints a new visit id). Booking a different property
   is "+ New visit" at the top, and goes through the normal planner. The two are not
   interchangeable and the backend stages them differently.

   Which actions a row offers is decided by its status, because Core enforces the same
   rules and would just reject the rest:
     upcoming  → Reschedule (same id) · Complete · Cancel
     completed → Schedule revisit
     cancelled → nothing
*/
import { useState } from "react";
import { createPortal } from "react-dom";
import {
  SM_FEEDBACK_QUESTIONS,
  VISIT_LEAD_STATUS,
  type CompleteVisitIn,
  type CrmVisitRow,
} from "../lib/api";
import {
  useCancelVisit,
  useCompleteVisit,
  useLeadCrmVisits,
  useRescheduleVisit,
  useRevisitVisit,
} from "../lib/queries";
import { useModalExit } from "../lib/useModalExit";
import { useToast } from "../components/Toast";
import { SLOTS, next7Days, isSlotDisabled } from "../lib/slots";
import { IconX, IconCalendar } from "../components/icons";

interface Props {
  leadId: string;
  leadName?: string | null;
  onNewVisit: () => void;
  onClose: () => void;
}

/* Which row is showing a form, and which one. Only ever one at a time — two open forms
   in a list this short is noise, and the actions are mutually exclusive anyway. */
type OpenForm = { visitId: number; kind: "reschedule" | "revisit" | "complete" } | null;

export default function ManageVisitsModal({ leadId, leadName, onNewVisit, onClose: rawClose }: Props) {
  const { onClose, overlayClass } = useModalExit(rawClose);
  const visits = useLeadCrmVisits(leadId);
  const [form, setForm] = useState<OpenForm>(null);

  const rows = visits.data?.items ?? [];
  /* Upcoming first, then by date descending — what you can still act on is what you
     came here for; the rest is history. */
  const order = { upcoming: 0, completed: 1, cancelled: 2 } as const;
  const sorted = [...rows].sort(
    (a, b) =>
      (order[a.status] ?? 3) - (order[b.status] ?? 3) ||
      (b.selected_date ?? "").localeCompare(a.selected_date ?? ""),
  );

  return createPortal(
    <div className={overlayClass} onClick={onClose}>
      <div className="modal mv-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Manage visits">
        <div className="mv-head">
          <div>
            <h3>Manage visits</h3>
            {leadName && <div className="mv-sub">{leadName}</div>}
          </div>
          <button className="modal-x" onClick={onClose} aria-label="Close"><IconX /></button>
        </div>

        <button className="mv-new" onClick={onNewVisit}>
          <span className="mv-plus">+</span> New visit
          <span className="mv-newhint">book a different property</span>
        </button>

        <div className="mv-list">
          {visits.isLoading && <div className="mv-empty">Loading visits…</div>}
          {!visits.isLoading && sorted.length === 0 && (
            <div className="mv-empty">No visits booked yet. Use “+ New visit” to book the first one.</div>
          )}
          {sorted.map((v) => (
            <VisitRow
              key={v.visit_id}
              v={v}
              leadId={leadId}
              form={form?.visitId === v.visit_id ? form.kind : null}
              setForm={setForm}
            />
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}

function VisitRow({
  v, leadId, form, setForm,
}: {
  v: CrmVisitRow;
  leadId: string;
  form: "reschedule" | "revisit" | "complete" | null;
  setForm: (f: OpenForm) => void;
}) {
  const close = () => setForm(null);
  const open = (kind: "reschedule" | "revisit" | "complete") => setForm({ visitId: v.visit_id, kind });

  return (
    <div className={`mv-row mv-${v.status}`}>
      <div className="mv-rowtop">
        <div className="mv-where">
          <div className="mv-society">{v.society || `Home ${v.home_id ?? "—"}`}</div>
          <div className="mv-meta">
            {[v.city, v.selected_date, v.selected_time].filter(Boolean).join(" · ") || "No slot recorded"}
          </div>
        </div>
        <span className={`mv-status mv-st-${v.status}`}>{v.status}</span>
      </div>

      {v.sales_feedback && <div className="mv-feedback">{v.sales_feedback}</div>}

      <div className="mv-actions">
        {v.status === "upcoming" && (
          <>
            <button className="btn ghost sm" onClick={() => (form === "reschedule" ? close() : open("reschedule"))}>Reschedule</button>
            <button className="btn ghost sm" onClick={() => (form === "complete" ? close() : open("complete"))}>Complete</button>
            <CancelButton visitId={v.visit_id} leadId={leadId} />
          </>
        )}
        {v.status === "completed" && (
          <button className="btn ghost sm" onClick={() => (form === "revisit" ? close() : open("revisit"))}>
            <IconCalendar /> Schedule revisit
          </button>
        )}
        {v.status === "cancelled" && <span className="mv-none">Cancelled — nothing to do</span>}
      </div>

      {(form === "reschedule" || form === "revisit") && (
        <SlotForm kind={form} visitId={v.visit_id} leadId={leadId} society={v.society} onDone={close} />
      )}
      {form === "complete" && <CompleteForm visitId={v.visit_id} leadId={leadId} onDone={close} />}
    </div>
  );
}

function CancelButton({ visitId, leadId }: { visitId: number; leadId: string }) {
  const toast = useToast();
  const cancel = useCancelVisit(leadId);
  const [confirm, setConfirm] = useState(false);

  /* Two-step rather than a window.confirm: cancelling writes straight through to
     Openhouse and can't be undone from here. */
  if (!confirm) return <button className="btn ghost sm mv-danger" onClick={() => setConfirm(true)}>Cancel visit</button>;
  return (
    <span className="mv-confirm">
      Cancel this visit?
      <button
        className="btn sm mv-danger-solid"
        disabled={cancel.isPending}
        onClick={() =>
          cancel.mutate(visitId, {
            onSuccess: () => toast("Visit cancelled on Openhouse", "green"),
            onError: (e: unknown) => toast(errText(e), "gold"),
          })
        }
      >
        {cancel.isPending ? "Cancelling…" : "Yes, cancel"}
      </button>
      <button className="btn ghost sm" onClick={() => setConfirm(false)}>Keep it</button>
    </span>
  );
}

/* Reschedule and revisit take exactly the same input — a date and a slot — and differ
   only in which endpoint they hit and what that does to the visit id. One form. */
function SlotForm({
  kind, visitId, leadId, society, onDone,
}: {
  kind: "reschedule" | "revisit";
  visitId: number;
  leadId: string;
  society: string | null;
  onDone: () => void;
}) {
  const toast = useToast();
  const days = next7Days();
  const [date, setDate] = useState(days[0]?.date ?? "");
  const [slot, setSlot] = useState("");
  const reschedule = useRescheduleVisit(leadId);
  const revisit = useRevisitVisit(leadId);
  const m = kind === "reschedule" ? reschedule : revisit;

  const submit = () =>
    m.mutate(
      { visitId, date, time: slot },
      {
        onSuccess: () => {
          toast(
            kind === "reschedule" ? "Visit moved to the new slot" : `Revisit booked at ${society || "the same property"}`,
            "green",
          );
          onDone();
        },
        onError: (e: unknown) => toast(errText(e), "gold"),
      },
    );

  return (
    <div className="mv-form">
      <div className="mv-formhead">
        {kind === "reschedule"
          ? "Move this visit to a new slot — same visit, same property."
          : `Book ${society || "this property"} again for the same buyer.`}
      </div>

      <div className="mv-days">
        {days.map((d) => (
          <button
            key={d.date}
            className={`mv-day${d.date === date ? " on" : ""}`}
            onClick={() => setDate(d.date)}
          >
            <span className="mv-dow">{d.dow}</span>
            <span className="mv-daynum">{d.dayNum}</span>
            <span className="mv-mon">{d.month}</span>
          </button>
        ))}
      </div>

      <div className="mv-slots">
        {SLOTS.map((s) => {
          const off = isSlotDisabled(date, s.startHour);
          return (
            <button
              key={s.label}
              className={`mv-slot${s.label === slot ? " on" : ""}`}
              disabled={off}
              title={off ? "This slot has already started today" : undefined}
              onClick={() => setSlot(s.label)}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <div className="mv-formfoot">
        <button className="btn ghost sm" onClick={onDone}>Back</button>
        <button className="btn primary sm" disabled={!date || !slot || m.isPending} onClick={submit}>
          {m.isPending ? "Saving…" : kind === "reschedule" ? "Reschedule" : "Book revisit"}
        </button>
      </div>
    </div>
  );
}

function CompleteForm({ visitId, leadId, onDone }: { visitId: number; leadId: string; onDone: () => void }) {
  const toast = useToast();
  const complete = useCompleteVisit(leadId);
  const [leadStatus, setLeadStatus] = useState("");
  const [feedback, setFeedback] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const submit = () => {
    const body: CompleteVisitIn = { sales_feedback: feedback.trim() };
    if (leadStatus) body.lead_status = leadStatus;
    /* Only answered questions are sent. Core reads the presence of sm_demand_feedback to
       decide the assisted path, so a form of empty strings would claim a feedback form
       was filled when it wasn't. */
    const given = Object.fromEntries(Object.entries(answers).filter(([, a]) => a));
    if (Object.keys(given).length) body.sm_feedback = given;
    complete.mutate(
      { visitId, body },
      {
        onSuccess: () => { toast("Visit marked complete", "green"); onDone(); },
        onError: (e: unknown) => toast(errText(e), "gold"),
      },
    );
  };

  return (
    <div className="mv-form">
      <div className="mv-formhead">Mark this visit complete and record what happened.</div>

      <label className="mv-field">
        <span>Lead status</span>
        <select className="ctl" value={leadStatus} onChange={(e) => setLeadStatus(e.target.value)}>
          <option value="">— not set —</option>
          {VISIT_LEAD_STATUS.map((s) => (
            <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
          ))}
        </select>
      </label>

      {SM_FEEDBACK_QUESTIONS.map((q) => (
        <label className="mv-field" key={q.key}>
          <span>{q.label}</span>
          <select
            className="ctl"
            value={answers[q.key] ?? ""}
            onChange={(e) => setAnswers((a) => ({ ...a, [q.key]: e.target.value }))}
          >
            <option value="">— skip —</option>
            {q.options.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>
      ))}

      <label className="mv-field mv-field-wide">
        <span>Sales feedback</span>
        <textarea
          rows={3}
          value={feedback}
          placeholder="What happened on the visit?"
          onChange={(e) => setFeedback(e.target.value)}
        />
      </label>

      <div className="mv-formfoot">
        <button className="btn ghost sm" onClick={onDone}>Back</button>
        <button className="btn primary sm" disabled={complete.isPending} onClick={submit}>
          {complete.isPending ? "Saving…" : "Mark complete"}
        </button>
      </div>
    </div>
  );
}

/* Core's own message is the useful one ("This visit is already created.", "Only upcoming
   visits can be rescheduled.") — it says what to do next, which a generic failure can't. */
function errText(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  return m || "That didn't go through";
}
