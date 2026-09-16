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
     cancelled → New visit (book that property again)

   ⚠️ "New visit" on a CANCELLED row is not a revisit and does not use Core's revisit
   endpoint — that one only clones a COMPLETED visit, and a cancelled visit never
   happened. It goes through the ordinary booking path with the details stored on the
   cancelled row, so the backend counts it as the buyer's FIRST visit to that property.
*/
import { useState } from "react";
import { createPortal } from "react-dom";
import {
  SM_FEEDBACK_QUESTIONS,
  VISIT_DETAIL_GROUPS,
  VISIT_DETAIL_LABELS,
  VISIT_LEAD_STATUS,
  type CompleteVisitIn,
  type CrmVisitRow,
} from "../lib/api";
import {
  useCancelVisit,
  useCompleteVisit,
  useLeadCrmVisits,
  useRebookProperty,
  useRescheduleVisit,
  useRevisitVisit,
  useVisitDetails,
} from "../lib/queries";
import { useModalExit } from "../lib/useModalExit";
import { useToast } from "../components/Toast";
import { SLOTS, next7Days, isSlotDisabled } from "../lib/slots";
import { IconX, IconCalendar, IconChevronRight } from "../components/icons";

interface Props {
  leadId: string;
  leadName?: string | null;
  onNewVisit: () => void;
  onClose: () => void;
}

/* Which row is showing a form, and which one. Only ever one at a time — two open forms
   in a list this short is noise, and the actions are mutually exclusive anyway. */
type OpenForm = { visitId: number; kind: "reschedule" | "revisit" | "complete" | "rebook" } | null;

/* A cancelled visit can only be re-booked if we still hold what the booking API needs. */
const canRebook = (v: CrmVisitRow) =>
  v.home_id != null && !!v.buyer_name?.trim() && (v.buyer_mobile ?? "").replace(/\D/g, "").length >= 5;

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
  form: "reschedule" | "revisit" | "complete" | "rebook" | null;
  setForm: (f: OpenForm) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const close = () => setForm(null);
  const open = (kind: NonNullable<OpenForm>["kind"]) => setForm({ visitId: v.visit_id, kind });

  return (
    <div className={`mv-row mv-${v.status}`}>
      {/* The whole header toggles the full record. A <button> rather than a click
          handler on the div, so it's reachable by keyboard and announces its state. */}
      <button className="mv-rowtop" aria-expanded={expanded} onClick={() => setExpanded((x) => !x)}>
        {/* Disclosure chevron, LEFT of the name: points right when closed and turns down
            when open. It was a "▾" glyph at the far right, which rendered at ~6px and sat
            beside the status pill where it read as part of the pill. */}
        <span className={`mv-caret${expanded ? " on" : ""}`} aria-hidden><IconChevronRight /></span>
        <div className="mv-where">
          <div className="mv-society">{v.society || `Home ${v.home_id ?? "—"}`}</div>
          <div className="mv-meta">
            {[v.city, v.selected_date, v.selected_time].filter(Boolean).join(" · ") || "No slot recorded"}
          </div>
        </div>
        <span className={`mv-status mv-st-${v.status}`}>{v.status}</span>
      </button>

      {v.sales_feedback && <div className="mv-feedback">{v.sales_feedback}</div>}

      {expanded && <VisitDetailPanel visitId={v.visit_id} />}

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
        {v.status === "cancelled" && (
          canRebook(v)
            ? <button className="btn ghost sm" onClick={() => (form === "rebook" ? close() : open("rebook"))}>
                <IconCalendar /> New visit
              </button>
            /* the old sheet-synced rows kept no buyer — say why rather than offer a
               button that can only fail validation on the way to Core */
            : <span className="mv-none">No buyer details stored — book from “+ New visit”</span>
        )}
      </div>

      {(form === "reschedule" || form === "revisit" || form === "rebook") && (
        <SlotForm kind={form} v={v} leadId={leadId} onDone={close} />
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

/* All three slot-picking actions take the same input — a date and a slot — and differ
   only in where they send it and what that does to the visit id:
     reschedule → same visit, moved
     revisit    → new visit id, cloned by Core from a COMPLETED visit
     rebook     → new visit via the ordinary booking path, because a CANCELLED visit
                  can't be cloned and never counted as a visit in the first place
   One form, because three near-identical date pickers is how they drift apart. */
function SlotForm({
  kind, v, leadId, onDone,
}: {
  kind: "reschedule" | "revisit" | "rebook";
  v: CrmVisitRow;
  leadId: string;
  onDone: () => void;
}) {
  const toast = useToast();
  const days = next7Days();
  const [date, setDate] = useState(days[0]?.date ?? "");
  const [slot, setSlot] = useState("");
  const reschedule = useRescheduleVisit(leadId);
  const revisit = useRevisitVisit(leadId);
  const rebook = useRebookProperty(leadId);
  /* NOT aliased into one `m`: the three mutations take different payloads, and a union
     of them type-checks as the INTERSECTION — every call would have to satisfy all three. */
  const pending = reschedule.isPending || revisit.isPending || rebook.isPending;
  const society = v.society;

  const done = (msg: string) => { toast(msg, "green"); onDone(); };
  const fail = (e: unknown) => toast(errText(e), "gold");

  const submit = () => {
    if (kind === "rebook") {
      /* Rebuilt from the cancelled row, not from the planner: the property, the buyer and
         the accompanying RM are all already decided — this is the same visit that was
         called off. `source` carries over so attribution isn't rewritten as "direct". */
      rebook.mutate(
        {
          selected_date: date, selected_time: slot,
          source: v.source || "direct",
          rm_accompanying: v.rm_accompanying,
          sales_manager_id: v.smid,
          lead_id: leadId,
          visits: [{
            home_id: v.home_id as number, city: v.city,
            buyer_name: v.buyer_name as string, buyer_mobile: v.buyer_mobile as string,
            society: v.society,
          }],
        },
        {
          onSuccess: (res: unknown) => {
            /* Booking answers 200 with a PER-UNIT result, so a failure arrives inside a
               success. Reporting "booked" off the HTTP status would be a lie. */
            const r = (res as { results?: { ok: boolean; error?: string }[] }).results?.[0];
            if (r && !r.ok) return fail(new Error(r.error || "Openhouse refused the booking"));
            done(`New visit booked at ${society || "that property"}`);
          },
          onError: fail,
        },
      );
      return;
    }
    const args = { visitId: v.visit_id, date, time: slot };
    if (kind === "reschedule") {
      reschedule.mutate(args, { onSuccess: () => done("Visit moved to the new slot"), onError: fail });
    } else {
      revisit.mutate(args, {
        onSuccess: () => done(`Revisit booked at ${society || "the same property"}`), onError: fail });
    }
  };

  return (
    <div className="mv-form">
      <div className="mv-formhead">
        {kind === "reschedule"
          ? "Move this visit to a new slot — same visit, same property."
          : kind === "revisit"
          ? `Book ${society || "this property"} again for the same buyer.`
          /* not a revisit: the cancelled visit never happened, so this is a first visit */
          : `Re-book ${society || "this property"} for the same buyer. The cancelled visit didn’t happen, so this counts as a first visit, not a revisit.`}
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
        <button className="btn primary sm" disabled={!date || !slot || pending} onClick={submit}>
          {pending ? "Saving…" : kind === "reschedule" ? "Reschedule" : kind === "revisit" ? "Book revisit" : "Book visit"}
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

/* The full Core record for one visit, fetched on first expand.

   ⚠️ Five fields are missing on purpose — profession, broker name / contact / alt
   contact, and company name. They are excluded SERVER-SIDE (HIDDEN_FIELDS in
   services/app_visit_data.py builds the SELECT), so they never reach the browser and
   can't be put back by editing this file.

   Unlabelled keys still render, with the column name prettified: Core adds fields, and a
   value showing up under a rough label beats it silently not showing up at all. */
function VisitDetailPanel({ visitId }: { visitId: number }) {
  const { data, isLoading, isError } = useVisitDetails(visitId);

  if (isLoading) return <div className="mv-detail mv-none">Loading visit record…</div>;
  if (isError || !data) return <div className="mv-detail mv-none">Couldn’t load this visit’s record.</div>;

  const core = data.core ?? {};
  const listed = new Set(VISIT_DETAIL_GROUPS.flatMap((g) => g.keys));
  const extra = Object.keys(core).filter((k) => !listed.has(k));
  const groups = [
    ...VISIT_DETAIL_GROUPS,
    ...(extra.length ? [{ title: "Other", keys: extra }] : []),
  ];

  return (
    <div className="mv-detail">
      {!data.core && (
        <div className="mv-note">
          Openhouse’s own record hasn’t been pulled for this visit yet — showing what we
          stored when it was booked.
        </div>
      )}

      {data.core &&
        groups.map((g) => {
          const rows = g.keys
            .map((k) => [k, core[k]] as const)
            .filter(([, val]) => val !== null && val !== undefined && val !== "" &&
                                 !(Array.isArray(val) && val.length === 0));
          if (!rows.length) return null;
          return (
            <div className="mv-dgroup" key={g.title}>
              <div className="mv-dtitle">{g.title}</div>
              {rows.map(([k, val]) => (
                <div className="mv-drow" key={k}>
                  <span className="mv-dkey">{VISIT_DETAIL_LABELS[k] ?? prettify(k)}</span>
                  <span className="mv-dval">{render(val)}</span>
                </div>
              ))}
            </div>
          );
        })}

      {/* Ours, not Core's — who booked it and who is going. Core has no idea about
          either, so this group is always shown. */}
      <div className="mv-dgroup">
        <div className="mv-dtitle">Booked by us</div>
        {(["booked_by", "rm_accompanying", "buyer_mobile", "source"] as const).map((k) => {
          const val = data.booking[k];
          if (val === null || val === undefined || val === "") return null;
          return (
            <div className="mv-drow" key={k}>
              <span className="mv-dkey">{VISIT_DETAIL_LABELS[k] ?? prettify(k)}</span>
              <span className="mv-dval">{render(val)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const prettify = (k: string) => k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function render(v: unknown): string {
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.length ? JSON.stringify(v) : "—";
  if (v && typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/* Core's own message is the useful one ("This visit is already created.", "Only upcoming
   visits can be rescheduled.") — it says what to do next, which a generic failure can't. */
function errText(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  return m || "That didn't go through";
}
