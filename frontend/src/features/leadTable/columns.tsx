/* Every column a lead table can show — one registry for All Leads, New Leads, Call Back
   Again and the five segment pages.

   Before this, each of those four files hand-wrote its own <th> and <td> for the same
   columns, and hand-counted `colSpan` to match. A column added to one page silently left
   the empty-state row a cell short on the others. Now a page just lists column ids; the
   header, the cell, the sort and the span all come from here.

   `popup` marks a field that used to be visible ONLY in the lead popup. Column settings
   groups them separately so they read as "bring this out of the popup", not as a column
   the page forgot. */
import type { CSSProperties, ReactNode } from "react";
import type { Lead } from "../../lib/api";
import { formatDate, formatDateTime, useMarkHot } from "../../lib/queries";
import { isNewToday, planClass, sourcesLabel, stageLabel } from "../../lib/leads";
import { ArrivalCount, NewBadge, SourceChips, StageChip } from "../../components/StageChip";
import { AssignControl } from "../../components/AssignControl";
import { CallButton } from "../../components/CallButton";
import LeadPhone from "../../components/LeadPhone";
import { NotesCell } from "../../components/NotesCell";
import { VisitsCell } from "../../components/VisitsCell";
import { IconCalendar, IconClock, IconStar } from "../../components/icons";

/** What a cell may need from the page it sits on. */
export interface LeadColCtx {
  /** All Leads is a read-only overview — owner is text there, not a picker */
  assignReadOnly?: boolean;
  /** segment pages fold the visit status into the stage cell */
  stageWithVisit?: boolean;
  /** opens Manage visits; the Actions column renders nothing without it */
  onManageVisits?: (l: Lead) => void;
}

type SortVal = string | number | null | undefined;

/* What column settings needs of a column: an id, a label, and whether it came from the
   popup. A table with its own columns (Demand Dashboard) satisfies this and reuses the
   modal; LeadColumn adds the rendering on top. */
export interface ColumnMeta {
  id: string;
  label: string;
  popup?: boolean;
}

export interface LeadColumn extends ColumnMeta {
  id: string;
  label: string;
  /** present = sortable; the column id is the sort key */
  sort?: (l: Lead) => SortVal;
  /** interactive cell — its clicks must not open the lead popup behind it */
  interactive?: boolean;
  /** was only ever visible inside the lead popup */
  popup?: boolean;
  thStyle?: CSSProperties;
  tdClass?: string;
  tdStyle?: CSSProperties;
  render: (l: Lead, ctx: LeadColCtx) => ReactNode;
}

const dash = <span style={{ color: "var(--muted)" }}>—</span>;
const t = (s: string | null | undefined): number | null => (s ? Date.parse(s) : null);
const mono: CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)" };
const small: CSSProperties = { fontSize: 12.5, color: "var(--ink-2)" };
const text = (v: string | null | undefined) => v || dash;

/* ── cells with behaviour of their own ──────────────────────────────────────── */

export function PlanChip({ plan }: { plan: string | null }) {
  if (!plan) return dash;
  return <span className={`plan-chip ${planClass(plan)}`}>{plan}</span>;
}

export function DueChip({ at }: { at: string | null }) {
  if (!at) return <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>;
  const mins = Math.round((new Date(at).getTime() - Date.now()) / 60000);
  const label = new Date(at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  let cls = "", suffix = "";
  if (mins < 0) { cls = " overdue"; suffix = ` · ${Math.abs(mins) >= 60 ? Math.round(Math.abs(mins) / 60) + "h" : Math.abs(mins) + "m"} late`; }
  else if (mins < 60) { cls = " soon"; suffix = ` · in ${mins}m`; }
  return <span className={`fu-chip${cls}`}><IconClock /> {label}{suffix}</span>;
}

/* Callback due on a lead that isn't in the callback worklist. Only overdue/today are
   worth flagging — a callback next week is noise in a name cell. */
function DueBadge({ at }: { at: string | null }) {
  if (!at) return null;
  const mins = Math.round((new Date(at).getTime() - Date.now()) / 60000);
  if (mins > 1440) return null;
  return (
    <span className={"fu-chip" + (mins < 0 ? " overdue" : " soon")} style={{ marginLeft: 6 }}>
      <IconClock /> {mins < 0 ? "callback overdue" : "callback due"}
    </span>
  );
}

function HotStar({ lead }: { lead: Lead }) {
  const mark = useMarkHot();
  return (
    <button
      className={"hot-star" + (lead.is_hot ? " on" : "")}
      title={lead.is_hot ? "Unmark as hot" : "Mark as hot"}
      disabled={mark.isPending}
      onClick={(e) => { e.stopPropagation(); mark.mutate({ id: lead.id, hot: !lead.is_hot }); }}
    >
      <span style={{ opacity: lead.is_hot ? 1 : 0.3 }}><IconStar /></span>
    </button>
  );
}

const yesNo = (v: boolean | null | undefined) => (v ? "Yes" : "No");

/* ── the registry ───────────────────────────────────────────────────────────── */

export const LEAD_COLUMNS: LeadColumn[] = [
  // — the columns the tables already had —
  { id: "hot", label: "Hot", interactive: true, thStyle: { width: 34 },
    sort: (l) => (l.is_hot ? 1 : 0), render: (l) => <HotStar lead={l} /> },
  { id: "name", label: "Lead", sort: (l) => l.name, thStyle: { width: 230 }, tdClass: "lead-cell",
    render: (l) => (
      <div className="nm" title={l.name ?? ""}>
        {isNewToday(l) && <NewBadge size={18} style={{ marginRight: 6 }} />}
        {l.name}<ArrivalCount lead={l} />
        {l.is_test && <span className="bucket-tag" style={{ marginLeft: 6 }}>TEST</span>}
        {/* RNR and Future Prospect keep their own stage but share the Rejected page —
            the badge is what tells a parked buyer apart from a dead one */}
        {l.stage === "rnr" && <span className="bucket-tag" style={{ marginLeft: 6 }}>RNR</span>}
        {l.stage === "future_prospect" && <span className="bucket-tag" style={{ marginLeft: 6 }}>FUTURE PROSPECT</span>}
        {/* qualified leads don't sit in Follow-up, so a due callback must show here */}
        {l.stage === "qualified" && <DueBadge at={l.follow_up_at} />}
      </div>
    ) },
  { id: "phone", label: "Phone", sort: (l) => l.phone, interactive: true, tdClass: "ph-cell",
    render: (l) => (
      <div className="phone-cell">
        <CallButton leadId={l.id} disabled={!l.phone} />
        <LeadPhone phone={l.phone} missCount={l.miss_count} />
      </div>
    ) },
  { id: "source", label: "Source", sort: (l) => sourcesLabel(l), tdClass: "cell-tight",
    render: (l) => <SourceChips lead={l} /> },
  { id: "stage", label: "Stage", sort: (l) => stageLabel(l.stage), tdClass: "cell-tight",
    render: (l, ctx) => ctx.stageWithVisit && l.visit_status
      ? <VisitsCell leadId={l.id} status={l.visit_status} date={l.visit_date}
                    society={l.visit_society} rm={l.visit_rm} count={l.visit_count} />
      : <StageChip stage={l.stage} /> },
  { id: "city", label: "City", sort: (l) => l.city, tdClass: "cell-tight", tdStyle: { fontSize: 12.5 },
    render: (l) => text(l.city) },
  { id: "society", label: "Society", sort: (l) => l.society, tdClass: "cell-text", tdStyle: small,
    render: (l) => <span title={l.society || ""}>{l.society || "—"}</span> },
  { id: "budget", label: "Budget", sort: (l) => l.budget_band, tdClass: "cell-tight", tdStyle: { fontSize: 12.5 },
    render: (l) => text(l.budget_band) },
  { id: "plan", label: "Plan to Buy", sort: (l) => l.plan_to_buy,
    render: (l) => <PlanChip plan={l.plan_to_buy} /> },
  { id: "due", label: "Follow-up due", sort: (l) => t(l.follow_up_at), tdClass: "cell-tight",
    render: (l) => <DueChip at={l.follow_up_at} /> },
  { id: "misses", label: "Misses", sort: (l) => l.miss_count,
    render: (l) => l.miss_count > 0
      ? <span className={"miss-chip" + (l.miss_count >= 5 ? " hot" : "")}>{l.miss_count} miss</span>
      : <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span> },
  { id: "reason", label: "Reject reason", sort: (l) => l.reject_reason, tdClass: "reason-cell",
    render: (l) => <span className="stage lost">{l.reject_reason || "—"}</span> },
  { id: "rejectNote", label: "Reject note", tdClass: "note-cell",
    // clamped to two lines; the full note is in the tooltip and on the lead itself
    render: (l) => <div className="note-clamp" title={l.reject_notes || undefined}>{l.reject_notes || "—"}</div> },
  { id: "created", label: "Created On", sort: (l) => t(l.received_at), tdClass: "cell-tight", tdStyle: mono,
    render: (l) => (l.received_at ? formatDate(l.received_at) : "—") },
  { id: "rejectedOn", label: "Rejected On", sort: (l) => t(l.rejected_at), tdClass: "cell-tight", tdStyle: mono,
    render: (l) => (l.rejected_at ? formatDate(l.rejected_at) : "—") },
  { id: "assigned", label: "Assigned To", sort: (l) => l.assigned_to, interactive: true,
    render: (l, ctx) => ctx.assignReadOnly
      ? (l.assigned_to || <span style={{ color: "var(--muted)" }}>Unassigned</span>)
      : <AssignControl leadId={l.id} assignedTo={l.assigned_to} /> },
  { id: "notes", label: "Notes", sort: (l) => t(l.latest_note_at), interactive: true,
    render: (l) => <NotesCell leadId={l.id} latest={l.latest_note} count={l.note_count} /> },
  { id: "activity", label: "Latest activity", sort: (l) => t(l.latest_activity_at), tdClass: "cell-tight", tdStyle: mono,
    render: (l) => (l.latest_activity_at ? formatDateTime(l.latest_activity_at) : "—") },
  { id: "actions", label: "Manage visits", interactive: true, tdStyle: { textAlign: "right", whiteSpace: "nowrap" },
    render: (l, ctx) => ctx.onManageVisits && (
      <button className="btn ghost sm" title="See and manage this lead's visits"
        onClick={(e) => { e.stopPropagation(); ctx.onManageVisits!(l); }}>
        <IconCalendar /> Manage visits
      </button>
    ) },

  // — fields that were only visible in the lead popup —
  { id: "email", label: "Email", popup: true, sort: (l) => l.email, tdClass: "cell-text", tdStyle: small,
    render: (l) => <span title={l.email || ""}>{l.email || "—"}</span> },
  { id: "configuration", label: "Configuration", popup: true, sort: (l) => l.configuration,
    tdClass: "cell-tight", tdStyle: { fontSize: 12.5 }, render: (l) => text(l.configuration) },
  { id: "visitDay", label: "Preferred visit day", popup: true, sort: (l) => l.preferred_visit_day,
    tdClass: "cell-tight", tdStyle: { fontSize: 12.5 }, render: (l) => text(l.preferred_visit_day) },
  { id: "remarks", label: "Source remarks", popup: true, sort: (l) => l.source_remarks, tdClass: "note-cell",
    render: (l) => <div className="note-clamp" title={l.source_remarks || undefined}>{l.source_remarks || "—"}</div> },
  { id: "assignedOn", label: "Assigned On", popup: true, sort: (l) => t(l.assigned_at), tdClass: "cell-tight", tdStyle: mono,
    render: (l) => (l.assigned_at ? formatDateTime(l.assigned_at) : "—") },
  { id: "qualifiedOn", label: "Qualified On", popup: true, sort: (l) => t(l.qualified_at), tdClass: "cell-tight", tdStyle: mono,
    render: (l) => (l.qualified_at ? formatDate(l.qualified_at) : "—") },
  { id: "stageSince", label: "In stage since", popup: true, sort: (l) => t(l.stage_changed_at), tdClass: "cell-tight", tdStyle: mono,
    render: (l) => (l.stage_changed_at ? formatDateTime(l.stage_changed_at) : "—") },
  { id: "visitDate", label: "Visit date", popup: true, sort: (l) => t(l.visit_date), tdClass: "cell-tight", tdStyle: mono,
    render: (l) => (l.visit_date ? formatDate(l.visit_date) : "—") },
  { id: "visitSociety", label: "Visit society", popup: true, sort: (l) => l.visit_society, tdClass: "cell-text", tdStyle: small,
    render: (l) => <span title={l.visit_society || ""}>{l.visit_society || "—"}</span> },
  { id: "visitRm", label: "Visit RM", popup: true, sort: (l) => l.visit_rm, tdStyle: small,
    render: (l) => text(l.visit_rm) },
  { id: "visitCount", label: "Visits", popup: true, sort: (l) => l.visit_count, tdClass: "cell-tight",
    render: (l) => (l.visit_count ? l.visit_count : dash) },
  { id: "missTotal", label: "Total misses", popup: true, sort: (l) => l.miss_total, tdClass: "cell-tight",
    render: (l) => (l.miss_total ? l.miss_total : dash) },
  { id: "connected", label: "Ever connected", popup: true, sort: (l) => (l.ever_connected ? 1 : 0), tdClass: "cell-tight",
    tdStyle: { fontSize: 12.5 }, render: (l) => yesNo(l.ever_connected) },
  { id: "arrivals", label: "Arrivals", popup: true, sort: (l) => l.count_leads_repeat, tdClass: "cell-tight",
    render: (l) => (l.count_leads_repeat ? l.count_leads_repeat : dash) },
  { id: "metaForm", label: "Meta form", popup: true, sort: (l) => (l.meta_lead_id ? 1 : 0), tdClass: "cell-tight",
    tdStyle: { fontSize: 12.5 }, render: (l) => yesNo(!!l.meta_lead_id) },
];

export const COLUMN_BY_ID: Record<string, LeadColumn> =
  Object.fromEntries(LEAD_COLUMNS.map((c) => [c.id, c]));

/* Sort accessors for useSort, built once. Module-level on purpose: useSort memoises on
   the accessors object, and the inline object every page used to pass was a new one on
   every render — so the table re-sorted on every keystroke in the search box. */
export const LEAD_SORTERS: Record<string, (l: Lead) => SortVal> = Object.fromEntries(
  LEAD_COLUMNS.filter((c) => c.sort).map((c) => [c.id, c.sort!]),
);
