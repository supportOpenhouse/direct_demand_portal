/* Lead Detail — source-captured data + the Q1-Q6 call-confirm form (saves to
   POST /v1/leads/:id/confirm). Mirrors the prototype's lead-detail left column. */
import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { formatDate, formatDateTime, formatPrice, useAddNote, useConfirmLead, useEntityActivity, useLatestVisit, useLead, useLeadMetaForm, useLeadNotes, useMarkPriority, usePatchSourceData, useSetFollowup, useSetLeadStage } from "../lib/queries";
import { ALL_STAGES, initials, leadSources, metaQuestionLabel, sourcesLabel, srcClass, srcLabel, stageLabel } from "../lib/leads";
import type { ActivityRow, Lead } from "../lib/api";
import { ArrivalCount, SourceChips } from "../components/StageChip";
import { actionStyle, Details, pretty } from "../lib/activity";
import { api, MetaFormDelivery } from "../lib/api";
import { useToast } from "../components/Toast";
import { AutocompleteChips, AutocompleteInput } from "../components/Autocomplete";
import { AssignControl } from "../components/AssignControl";
import {
  IconCalendar,
  IconEdit,
  IconHome,
  IconStar,
  IconWarn,
  IconClock,
  IconMeta,
} from "../components/icons";
import CallActivityCard from "../components/CallActivityCard";
import HuvoCallCard from "../components/HuvoCallCard";
import { useDebounce } from "../lib/useDebounce";
import { openInMaps } from "../lib/maps";
import { VisitPlanner } from "../features/VisitPlanner";
import ManageVisitsModal from "../features/ManageVisitsModal";
import { StageChip } from "../components/StageChip";

const PURPOSES = ["Self-use", "Investment"];
const CONFIGS = ["2 BHK", "2.5 BHK", "3 BHK", "3.5 BHK", "4 BHK"];
const PLANS = ["Within 30 days", "1–3 months", "3–6 months", "Just exploring"];
const CITIES = ["Noida", "Gurgaon", "Ghaziabad", "Faridabad", "Delhi"];

// (re-add Broker/Budget/Location here later — backend accepts them too)
/* The reject form (reason + notes) was removed on 15 Sep with the card's Reject button:
   the confirm card keeps a single Save. Rejecting is now the Status card's stage picker,
   which records NO reason — restore this modal if the Rejected page's reason filter and
   `leads.reject_reason` are wanted again. */

/* Stage, changeable to anything.

   Every other stage write in this app is forward-only on purpose — a qualify form
   re-submitted on a visited lead is a no-op, which is what stops the funnel from
   being walked backwards by accident. This control is the deliberate escape hatch
   for the case that guard creates: a lead put in the wrong stage could not be put
   back. It logs like any other stage move. */
function StatusCard({ lead }: { lead: any }) {
  const set = useSetLeadStage(lead.id);
  const toast = useToast();
  return (
    <div className="card panel-pad">
      <div className="panel-title">Status</div>
      {/* wrapped in .field so it inherits the full-width control styling — a bare
          <select> sizes to its longest option and leaves the card half empty */}
      <div className="field" style={{ marginBottom: 0 }}>
      <select
        value={lead.stage}
        disabled={set.isPending}
        onChange={(e) =>
          set.mutate(e.target.value, {
            onSuccess: (r: { after: string }) => toast(`Moved to ${stageLabel(r.after)}`, "green"),
            onError: (err: any) => toast(err.message, "gold"),
          })}
      >
        {ALL_STAGES.map((st: string) => <option key={st} value={st}>{stageLabel(st)}</option>)}
      </select>
      </div>
    </div>
  );
}

/* The lead's captured source data: its OWN source plus every source merged into it
   that has no Meta form ("WhatsApp + 99acres"). A merged source's row no longer exists
   — what it captured lives in its `lead_repeat` entry's metadata.lead — so each field
   shows the lead's own value, then any DIFFERENT value a merged source carried. */
// "+91 85955 94789" standing in for a name. Same pattern as the DB's rename in
// scripts/07_lead_sources.sql and scripts/11_fix_number_names.sql.
const PHONE_ONLY_NAME = /^\s*\+?[\d\s()-]{8,}\s*$/;

function SourceCard({ lead, merged }: { lead: any; merged: ActivityRow[] }) {
  const patch = usePatchSourceData(lead.id);
  const toast = useToast();
  const [edit, setEdit] = useState(false);
  const rows = merged.map((r) => (r.metadata.lead ?? {}) as Record<string, unknown>);
  // every distinct non-empty value, own first — no source's answer is hidden. Distinct
  // ignores case: a portal's "PUNEET BAWA" is the same answer as Meta's "Puneet Bawa".
  const all = (key: string): string[] => {
    const byLower = new Map<string, string>();
    for (const v of [lead[key], ...rows.map((x) => x[key])]) {
      const s = v == null ? "" : String(v).trim();
      // a WhatsApp lead is named after its number until someone knows better — that
      // is a placeholder, not a name, so it never shows beside the real one
      if (key === "name" && PHONE_ONLY_NAME.test(s)) continue;
      if (s && !byLower.has(s.toLowerCase())) byLower.set(s.toLowerCase(), s);
    }
    return [...byLower.values()];
  };
  const shown = (key: string) => all(key).join(" / ") || null;
  // Edit writes the lead's own columns, prefilled with the first value any source has
  const initial = () => ({
    city: all("city")[0] ?? "", society: all("society")[0] ?? "", budget_band: all("budget_band")[0] ?? "",
    plan_to_buy: all("plan_to_buy")[0] ?? "", source_remarks: all("source_remarks")[0] ?? "",
  });
  const [f, setF] = useState(initial);
  // keyed on ids, not the array: the parent rebuilds `merged` every render
  const mergedKey = merged.map((r) => r.id).join();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setF(initial()); }, [lead, mergedKey]);
  const title = [lead.source, ...merged.map((r) => String(r.metadata.source ?? ""))].map(srcLabel).join(" + ");

  const save = () =>
    patch.mutate(f, { onSuccess: () => { toast("Source data updated", "green"); setEdit(false); }, onError: (e: any) => toast(e.message, "gold") });

  /* Read-only values render as TEXT, not a disabled <input>. A greyed box invites
     a click that does nothing and makes a record look like an unfinished form. */
  const ro = (label: string, val: string | null) => (
    <div className="field-row">
      <span className="field-lbl">{label}</span>
      <span className="field-val">{val || "—"}</span>
    </div>
  );
  const inp = (label: string, key: keyof typeof f, placeholder = "") => (
    <div className="field"><label>{label}</label>
      <input value={f[key]} placeholder={placeholder} onChange={(e) => setF({ ...f, [key]: e.target.value })} /></div>
  );

  return (
    <div className="card panel-pad meta-card">
      <div className="panel-title" style={{ justifyContent: "space-between" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>Lead data captured from {title}</span>
        {edit ? (
          <span style={{ display: "flex", gap: 6 }}>
            <button className="btn ghost sm" onClick={() => setEdit(false)}>Cancel</button>
            <button className="btn green sm" onClick={save} disabled={patch.isPending}>{patch.isPending ? "Saving…" : "Save"}</button>
          </span>
        ) : (
          <button className="btn ghost sm" onClick={() => setEdit(true)}><IconEdit /> Edit</button>
        )}
      </div>
      {edit ? (
        <>
          <div className="two">
            {inp("Budget", "budget_band", "e.g. ₹70L – ₹90L")}
            <div className="field"><label>City</label>
              <select value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}>
                <option value="">Select…</option>
                {CITIES.map((c) => <option key={c}>{c}</option>)}
                {f.city && !CITIES.includes(f.city) && <option>{f.city}</option>}
              </select>
            </div>
          </div>
          <div className="field">
            <label>Society of interest <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— search master list</span></label>
            <AutocompleteInput
              value={f.society}
              placeholder="Search societies…"
              onPick={(label, hit) => setF((s) => ({ ...s, society: label, city: hit?.meta?.city || s.city }))}
              fetcher={async (q) => (await api.searchSocieties(q)).items.map((h) => ({ label: h.society, sub: [h.locality, h.city].filter(Boolean).join(", "), meta: h }))}
            />
          </div>
          <div className="two">
            <div className="field"><label>Plan to Buy</label>
              <select value={f.plan_to_buy} onChange={(e) => setF({ ...f, plan_to_buy: e.target.value })}>
                <option value="">Select…</option>{PLANS.map((p) => <option key={p}>{p}</option>)}
              </select></div>
            <div></div>
          </div>
          <div className="field" style={{ marginBottom: 0 }}><label>Source remarks</label>
            <input value={f.source_remarks} onChange={(e) => setF({ ...f, source_remarks: e.target.value })} /></div>
        </>
      ) : (
        <>
          <div className="two">{ro("Budget", shown("budget_band"))}{ro("City", shown("city"))}</div>
          {/* three short, related facts about what they asked for — one line */}
          <div className="three">
            {ro("Society of interest", shown("society"))}
            {ro("Plan to Buy", shown("plan_to_buy"))}
            {ro("Preferred visit day (from ad)", shown("preferred_visit_day"))}
          </div>
          {/* only when some source carried them — most portal rows never do */}
          {(shown("configuration") || shown("current_location") || shown("email")) && (
            <div className="three">
              {ro("Configuration", shown("configuration"))}
              {ro("Currently lives in", shown("current_location"))}
              {ro("Email", shown("email"))}
            </div>
          )}
          {/* a merged source that knew them by another name (a WhatsApp lead is often
              named after its number) */}
          {all("name").length > 1 && ro("Name", shown("name"))}
          {shown("source_remarks") && ro("Source remarks", shown("source_remarks"))}
        </>
      )}
    </div>
  );
}

/* Every question the ad actually asked, verbatim from `meta_lead_events.raw_lead`.
   The set differs per form and changes whenever marketing edits one, so nothing here
   may assume a fixed list of questions. */
/* The Instant Form exactly as Meta delivered it — read-only, because it is the
   delivery record and editing what the buyer typed would destroy the only copy of
   what they actually said.

   Presentational: the parent fetches, because whether this has content decides which
   card takes the slot beside "Conversation & remarks". */
function MetaFormCard({ deliveries, landscape = false }: {
  deliveries: MetaFormDelivery[];   // newest first
  /* full width under the pair — the Meta form of a lead whose card beside Remarks
     belongs to another source; the answers then flow into columns */
  landscape?: boolean;
}) {
  // A repeat submitter's answers can differ between submissions. The newest shows by
  // default; the "newest of N" label is the toggle that reveals the earlier ones.
  const [showAll, setShowAll] = useState(false);
  const shownForms = showAll ? deliveries : deliveries.slice(0, 1);
  const many = deliveries.length > 1;
  return (
    <div className={"card panel-pad" + (landscape ? " meta-form-wide" : "")}>
      <div className="panel-title">
        <IconMeta /> From the Meta form
        {many && (
          <button type="button" className="meta-form-n meta-form-toggle"
                  aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
            {showAll ? `all ${deliveries.length} submissions · hide earlier`
                     : `newest of ${deliveries.length} submissions`}
          </button>
        )}
      </div>
      {shownForms.map((d, i) => (
        <div key={d.meta_lead_id} className={i ? "meta-form-older" : undefined}>
          {showAll && many && (
            <div className="meta-form-when">
              {i === 0 ? "Newest" : "Earlier"} · submitted {d.received_at ? formatDateTime(d.received_at) : "—"}
            </div>
          )}
          {/* Which ad actually produced this submission. Omitted entirely when Meta sent
              neither — a test-tool submission has no campaign, and an empty bracket
              claims an attribution that does not exist. */}
          {(d.campaign_name || d.ad_name) && (
            <div className="meta-form-src">
              ({[d.campaign_name, d.ad_name].filter(Boolean).join(" · ")})
            </div>
          )}
          <div className="meta-form-rows">
            {d.responses.map((r) => (
              <div className="meta-form-row" key={r.question}>
                <span className="meta-form-q">{metaQuestionLabel(r.question)}</span>
                <span className="meta-form-a">{r.answer || "—"}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}


/* Everything activity_log holds for this lead, newest first.

   Rendered with the Logs page's own `Details` (lib/activity.tsx) rather than a second
   formatter, so one event cannot read two ways on two screens.

   Capped and scrolling like the note thread: a worked lead carries dozens of rows, and
   an uncapped list pushes every card below it off the bottom of the popup. */
function LeadHistory({ id }: { id: string }) {
  const { data, isLoading } = useEntityActivity("lead", id);
  const items = data?.items ?? [];
  return (
    <div className="card panel-pad">
      <div className="panel-title"><IconClock /> Lead history</div>
      {isLoading ? (
        <div className="lh-empty">Loading…</div>
      ) : !items.length ? (
        <div className="lh-empty">Nothing logged for this lead yet.</div>
      ) : (
        <div className="lh-list">
          {items.map((r) => (
            <div className="lh-row" key={r.id}>
              <div className="lh-top">
                <span className="lh-act" style={actionStyle(r)}>{pretty(r.action)}</span>
                <span className="lh-when">{formatDateTime(r.created_at)}</span>
              </div>
              <div className="lh-det"><Details r={r} /></div>
              <div className="lh-who">{r.actor_name || r.actor_email || "system"}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function NotesThread({ id }: { id: string }) {
  const { data, isLoading } = useLeadNotes(id);
  const addNote = useAddNote(id);
  const toast = useToast();
  const [text, setText] = useState("");
  const send = () => {
    const t = text.trim();
    if (!t) return;
    addNote.mutate(t, { onSuccess: () => setText(""), onError: (e: any) => toast(e.message, "gold") });
  };
  return (
    <div className="card panel-pad">
      <div className="panel-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>{" "}
        Conversation &amp; remarks
      </div>
      <div className="note-list">
        {isLoading ? (
          <div className="empty" style={{ padding: 14 }}>Loading…</div>
        ) : !data?.items.length ? (
          <div className="note-empty">No remarks yet — start the thread below.</div>
        ) : (
          data.items.map((n, i) => (
            <div key={n.id || `seed-${i}`} className={"note-item" + (n.source === "remarks" ? " imported" : "")}>
              <div className="note-text">{n.body}</div>
              <div className="note-meta">
                {n.author || "—"}{n.created_at ? ` · ${formatDateTime(n.created_at)}` : ""}
                {n.source === "remarks" && " · imported"}
              </div>
            </div>
          ))
        )}
      </div>
      <div className="note-composer">
        <input
          className="note-input"
          value={text}
          placeholder="Add a remark…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button className="btn primary sm" onClick={send} disabled={addNote.isPending || !text.trim()}>Send</button>
      </div>
    </div>
  );
}

/* The lead's only follow-up control. Since 15 Sep the confirm form below saves answers
   ONLY, so a callback is set here or not at all — hence no required marker and no
   `invalid` prop from that form. Starts EMPTY on every open so the RM enters a fresh
   callback for this call; the previously-stored time (`current`) is shown for reference
   and kept in the DB until a new one is saved. "Save & move" sets a plain callback. */
function FollowupWidget({ id, value, onChange, current }: { id: string; value: string; onChange: (v: string) => void; current: string | null }) {
  const nav = useNavigate();
  const toast = useToast();
  const set = useSetFollowup(id);
  const save = () => {
    if (!value) { toast("Follow-up is required — pick a date & time", "gold"); return; }
    set.mutate(new Date(value).toISOString(), {
      onSuccess: () => { toast("Follow-up scheduled · moved to Follow-up", "green"); nav("/leads/followup"); },
      onError: (e: any) => toast(e.message, "gold"),
    });
  };
  return (
    <div className="card panel-pad">
      <div className="panel-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="13" r="8" /><path d="M12 9v4l2 2M9 2h6" /></svg>{" "}
        Schedule a follow-up
      </div>
      {current && (
        <div className="fu-current">
          Currently set: <span className="fu-chip"><IconClock /> {formatDateTime(current)}</span>
        </div>
      )}
      <div className="fu-row">
        <input type="datetime-local" value={value} onChange={(e) => onChange(e.target.value)} />
        {/* Short label so the datetime beside it stays readable in a half-width
            card; the full sentence lives in the tooltip. */}
        <button className="btn green sm" onClick={save} disabled={set.isPending}
                title="Save the follow-up time and move this lead to the Follow-up list">
          {set.isPending ? "Saving…" : "Save & move →"}
        </button>
      </div>
    </div>
  );
}

/* `mobile` — same page, same behaviour, one column. The card order the phone asks for
   is the desktop set with the confirm form moved last, which is a layout concern, so
   the two columns collapse to a flex list (see .m-detail) instead of forking the JSX. */
function SavedVisitCard({ id, onEdit, booked }: { id: string; onEdit: () => void; booked: boolean }) {
  const { data, isLoading } = useLatestVisit(id);
  const plan = data?.plan;
  if (isLoading || !plan) return null;
  return (
    <div className="card panel-pad">
      <div className="panel-title" style={{ justifyContent: "space-between" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          📅 Planned site visits
          {/* a saved plan is internal prep, not an appointment — it no longer moves
              the lead, so say plainly that nothing is booked yet */}
          {!booked && (
            <span className="fu-chip" style={{ background: "var(--amber-soft)", color: "var(--amber-deep)" }}>
              Visit not scheduled yet
            </span>
          )}
        </span>
        <span style={{ display: "flex", gap: 6 }}>
          <button className="btn ghost sm" onClick={() => openInMaps(plan.start_lat != null && plan.start_lng != null ? { lat: plan.start_lat, lng: plan.start_lng } : null, plan.stops)}>↗ Maps</button>
          <button className="btn ghost sm" onClick={onEdit}>Edit plan</button>
        </span>
      </div>
      <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 10 }}>
        {plan.rm ? `${plan.rm} · ` : ""}{plan.trip_date ? formatDate(plan.trip_date) : "—"} ·{" "}
        <b style={{ color: "var(--ink-2)" }}>
          {plan.total_km != null ? `${plan.total_km} km` : "—"}{plan.total_min != null ? ` · ${Math.round(plan.total_min)} min` : ""}
        </b>{" "}
        {plan.route_source === "google" ? "(Google route)" : "(est.)"}
      </div>
      {plan.stops.map((s, i) => (
        <div key={i} className="itin-stop" style={{ marginBottom: 8 }}>
          <div className="num">{i + 1}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="sn">Visit {i + 1} · {s.name || s.society || "—"}</div>
            <div className="sl">{[s.locality].filter(Boolean).join(", ")}{s.price_text ? ` · ${s.price_text}` : ""}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* The lead's name, with a pencil to rename it. Any signed-in user can — a wrong name is
   usually spotted by whoever is on the call, and the activity log records who changed it.
   One component for both headers, so the popup and the page can't grow two name edits. */
function NameHeading({ lead, as }: { lead: Lead; as: "h2" | "h3" }) {
  const patch = usePatchSourceData(lead.id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(lead.name ?? "");
  const Tag = as;

  const save = () => {
    const name = draft.trim();
    // a blank name would leave the row with nothing to identify it by
    if (!name || name === (lead.name ?? "")) return setEditing(false);
    patch.mutate({ name }, { onSuccess: () => setEditing(false) });
  };

  if (editing) {
    return (
      <Tag className="lead-name">
        <input className="lead-name-input" autoFocus value={draft} disabled={patch.isPending}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
            if (e.key === "Escape") { setDraft(lead.name ?? ""); setEditing(false); }
          }}
          onBlur={save} />
      </Tag>
    );
  }
  return (
    <Tag className="lead-name">
      {lead.name || "Unnamed"}
      <button className="name-edit" title="Rename this lead" aria-label="Rename this lead"
        onClick={() => { setDraft(lead.name ?? ""); setEditing(true); }}>
        <IconEdit />
      </button>
      <ArrivalCount lead={lead} />
    </Tag>
  );
}

export default function LeadDetail({ mobile = false, leadId, inModal = false }: {
  mobile?: boolean;
  /** Set by the popup. Absent on the /leads/:id route, where the param wins. */
  leadId?: string;
  inModal?: boolean;
}) {
  const { id: routeId = "" } = useParams();
  const id = leadId ?? routeId;
  const nav = useNavigate();
  // Live Calls sends this in router state when "Yes" opens the lead in the same tab.
  const fromLiveCalls = (useLocation().state as { from?: string } | null)?.from === "live-calls";
  const toast = useToast();
  const { data: lead, isLoading } = useLead(id);
  /* Fetched HERE rather than inside the card, because what it returns decides which
     card goes in the pair below — a child can't make that call for its own slot.

     "Lead data captured from Meta" IS this form, normalised into our columns, so when
     the form itself is available the form wins and that card is not rendered at all:
     two cards of the same answers, one of them a lossy copy, reads worse than one. */
  // any lead Meta is ONE of the sources of — a Meta arrival merged into a
  // MagicBricks/WhatsApp lead still has its form
  const metaForm = useLeadMetaForm(id, !!lead && leadSources(lead).includes("meta"));
  const metaDeliveries = metaForm.data?.items ?? [];
  // Newest submission. A repeat submitter has more than one and the answers can
  // differ, so the card says how many rather than silently showing one of several.
  const latestForm = metaDeliveries[0];
  const hasMetaForm = !!latestForm?.responses.length;
  /* Every other source folded into this lead: each `lead_repeat` entry carries the
     arriving row in metadata.lead. Newest per source (the list is newest first). Shares
     the Lead history card's query, so it costs no extra request. These go INTO the
     source card beside Remarks ("WhatsApp + 99acres") — the full-width box is for a
     Meta form only, so a Meta arrival that has a form is left to that box. */
  const activity = useEntityActivity("lead", id);
  const seenSources = new Set<string>();
  const mergedSources = (activity.data?.items ?? []).filter((r) => {
    const src = String(r.metadata?.source ?? "");
    if (r.action !== "lead_repeat" || !r.metadata?.lead || !src || seenSources.has(src)) return false;
    seenSources.add(src);
    return src !== lead?.source && !(src === "meta" && hasMetaForm);
  });
  // The form takes the source card's slot only when Meta is the lead's own source AND
  // nothing else was merged in; otherwise the source card stays and the form goes
  // full width underneath.
  const formInPair = hasMetaForm && lead?.source === "meta" && mergedSources.length === 0;
  const confirm = useConfirmLead(id);
  const [planner, setPlanner] = useState(false);
  const [managing, setManaging] = useState(false);

  const [purpose, setPurpose] = useState("");
  const [budgetMin, setBudgetMin] = useState("");
  const [budgetMax, setBudgetMax] = useState("");
  const [config, setConfig] = useState("");
  const [sizeMin, setSizeMin] = useState("");
  const [sizeMax, setSizeMax] = useState("");
  const [micromarkets, setMicromarkets] = useState<string[]>([]);
  const [societies, setSocieties] = useState<string[]>([]);
  const [localities, setLocalities] = useState<string[]>([]);
  // cascaded "+" options — offered by the level above, never auto-selected
  const [localitySuggest, setLocalitySuggest] = useState<string[]>([]);
  const [societySuggest, setSocietySuggest] = useState<string[]>([]);
  const [remark, setRemark] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [showErr, setShowErr] = useState(false);

  // prefill from existing confirmed data + source-captured society
  useEffect(() => {
    if (!lead) return;
    const c = lead.confirmed_data;
    setPurpose(c?.purpose || "");
    setBudgetMin(c?.budget_min_lacs != null ? String(c.budget_min_lacs) : "");
    setBudgetMax(c?.budget_max_lacs != null ? String(c.budget_max_lacs) : "");
    setConfig(c?.configuration || lead.configuration || "");
    setSizeMin(c?.size_min_sqft != null ? String(c.size_min_sqft) : "");
    setSizeMax(c?.size_max_sqft != null ? String(c.size_max_sqft) : "");
    setMicromarkets(c?.preferred_micromarkets || []);
    setSocieties(c?.shortlisted_societies?.length ? c.shortlisted_societies : lead.society ? [lead.society] : []);
    setLocalities(c?.preferred_localities || []);
    setLocalitySuggest([]);
    setSocietySuggest([]);
    setRemark(c?.remark || "");
    setFollowUp("");  // always blank on open — RM enters a fresh follow-up for this connected call
  }, [lead]);

  // Cascade: a micro-market OFFERS its localities and their societies; a locality offers
  // its societies. Nothing is auto-selected — a micro-market can carry 30+ societies and
  // silently shortlisting all of them buries the handful the buyer actually named. The RM
  // picks from the "+" chips; picking one moves it into the selected (✕) chips.
  const suggestSocietiesFor = async (locs: string[]) => {
    const lists = await Promise.all(locs.map((l) => api.societiesByLocality(l).then((r) => r.items).catch(() => [])));
    const socs = lists.flat();
    if (socs.length) setSocietySuggest((prev) => Array.from(new Set([...prev, ...socs])));
  };
  const onMicromarketsChange = (next: string[]) => {
    const added = next.filter((m) => !micromarkets.includes(m));
    setMicromarkets(next);
    added.forEach(async (mm) => {
      try {
        const locs = (await api.localitiesByMicromarket(mm)).items;
        setLocalitySuggest((prev) => Array.from(new Set([...prev, ...locs])));
        suggestSocietiesFor(locs); // offer the second level too
      } catch { /* ignore */ }
    });
  };
  const onLocalitiesChange = (next: string[]) => {
    const added = next.filter((l) => !localities.includes(l));
    setLocalities(next);
    suggestSocietiesFor(added);
  };

  // live matching — recomputes (debounced) as any requirement field changes
  const bMin = parseFloat(budgetMin), bMax = parseFloat(budgetMax);
  const sMin = parseFloat(sizeMin), sMax = parseFloat(sizeMax);
  const reqKey = JSON.stringify({
    city: lead?.city ?? null,
    societies, localities, micromarkets,
    configuration: config || null,
    size_min_sqft: sMin > 0 ? sMin : null,
    size_max_sqft: sMax > 0 ? sMax : null,
    budget_min_lacs: bMin > 0 ? bMin : null,
    budget_max_lacs: bMax > 0 ? bMax : null,
    budget_band: lead?.budget_band ?? null,
  });

  if (isLoading) return <div className="card"><div className="empty" style={{ padding: 40 }}>Loading lead…</div></div>;
  if (!lead) return <div className="card"><div className="empty" style={{ padding: 40 }}>Lead not found.</div></div>;

  // a visit is booked — the card above shows it, and SavedVisitCard reads it
  const isPipeline = lead.stage === "visit_scheduled" || (lead.visit_count ?? 0) > 0;

  // the follow-up is NOT among these: this form no longer sets one (the Follow-up card
  // beside it owns that), so the only required fields are the starred answers
  const invalid = { purpose: !purpose, budget: !(bMin > 0 && bMax > 0 && bMax >= bMin), config: !config };
  const reqInvalid = invalid.purpose || invalid.budget || invalid.config;

  const basePayload = () => ({
    purpose,
    budget_min_lacs: bMin,
    budget_max_lacs: bMax,
    configuration: config,
    size_min_sqft: sMin > 0 ? sMin : null,
    size_max_sqft: sMax > 0 ? sMax : null,
    preferred_micromarkets: micromarkets,
    shortlisted_societies: societies,
    preferred_localities: localities,
    remark: remark || null,
  });

  // The only save this form has: persist the answers — no callback, no stage change.
  const saveOnly = () => {
    if (reqInvalid) {
      setShowErr(true);
      toast("Fill the required (*) fields", "gold");
      return;
    }
    confirm.mutate(
      { ...basePayload(), follow_up_at: null, qualify: false },
      {
        onSuccess: () => toast("Details saved", "green"),
        onError: (e) => toast(e.message, "gold"),
      }
    );
  };

  const field = (bad: boolean) => "field" + (showErr && bad ? " invalid" : "");

  return (
    <>
      {/* Page chrome only. In the popup there is nothing to go "back" to — you are
          still on the list, and ✕ / Escape / the backdrop close it.
          Arriving from Live Calls, "Back" has to be unambiguous: the RM is mid-shift
          and the campaign is still dialling them. nav(-1) would do it, but naming the
          destination is what makes it obvious they aren't leaving the queue behind. */}
      {!inModal && (fromLiveCalls ? (
        <div className="back" onClick={() => nav("/live-calls")}>← Live Calls</div>
      ) : (
        <div className="back" onClick={() => nav(-1)}>← Back</div>
      ))}
      {/* In the popup the header is one line of identity — name, where, which
          stage — with the detail underneath, matching Direct Inventory's detail
          modal. The page keeps its avatar-and-actions header, which has room for
          it. */}
      {inModal ? (
        <>
          <div className="lead-modal-head">
            <NameHeading lead={lead} as="h3" />
            {lead.city && <span className="chip-soft">{lead.city}</span>}
            {lead.is_test && <span className="chip-soft">Test</span>}
            <StageChip stage={lead.stage} />
            <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
              <AssignControl leadId={lead.id} assignedTo={lead.assigned_to} />
              {!mobile && <button className="btn ghost sm" onClick={() => setManaging(true)}><IconCalendar /> Manage visits</button>}
            </span>
          </div>
          <div className="lead-modal-sub">
            {[lead.phone, sourcesLabel(lead), lead.society, lead.configuration].filter(Boolean).join(" · ")}
            {lead.budget_band ? <> · <b>{lead.budget_band}</b></> : null}
          </div>
        </>
      ) : (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 14, marginBottom: 18 }}>
        <div className="lead-head">
          <div className="av">{initials(lead.name)}</div>
          <div>
            <div className="lead-name-row"><NameHeading lead={lead} as="h2" />{lead.is_test && <span className="bucket-tag" style={{ verticalAlign: "middle" }}>TEST</span>}</div>
            <div className="meta" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              {lead.phone}
              <SourceChips lead={lead} />
              <span style={{ color: "var(--muted)" }}>Assigned:</span>
              <AssignControl leadId={lead.id} assignedTo={lead.assigned_to} />
              {lead.confirmed && <span className="stage contacted">Qualified</span>}
            </div>
          </div>
        </div>
        <div className="lead-actions">
          {/* the planner is a wide drawer with a map — desktop only */}
          {!mobile && <button className="btn ghost" onClick={() => setManaging(true)}><IconCalendar /> Manage visits</button>}
        </div>
      </div>
      )}
      {managing && (
        <ManageVisitsModal
          leadId={id}
          leadName={lead.name}
          /* "+ New visit" is a DIFFERENT property, which is the planner's job */
          onNewVisit={() => { setManaging(false); setPlanner(true); }}
          onClose={() => setManaging(false)}
        />
      )}
      {planner && <VisitPlanner leadId={id} leadName={lead.name} leadCity={lead.city} leadPhone={lead.phone} onClose={() => setPlanner(false)} />}

      <div className={mobile ? "m-detail" : "detail-grid"}>
        <div className="dcol">
          {/* Cards pair by what the reader is doing with them — the record on the
              left, what to do about it on the right:

                STATUS / STAGE       | FOLLOW-UPS   where it is, when to call next
                CAPTURED FROM <src>  | REMARKS      what the form said, what was said back
          */}
          <div className="expand-pair">
            <StatusCard lead={lead} />
            <FollowupWidget id={id} value={followUp} onChange={setFollowUp} current={lead.follow_up_at} />
          </div>

          <div className="expand-pair">
            {formInPair
              ? <MetaFormCard deliveries={metaDeliveries} />
              : <SourceCard lead={lead} merged={mergedSources} />}
            <NotesThread id={id} />
          </div>

          {/* the Meta form, full width, when the card above is another source's */}
          {hasMetaForm && !formInPair && <MetaFormCard deliveries={metaDeliveries} landscape />}

          {/* CONFIRMED call form — last on mobile, per the requested card order */}
          <div className={"card panel-pad compact-form" + (mobile ? " m-last" : "")}>
            <div className="panel-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" />
              </svg>{" "}
              Lead data confirmed on call
            </div>

            <div className="two">
              <div className={field(invalid.purpose)}>
                <label>Q1. Purpose <span className="req">*</span></label>
                <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
                  <option value="">Select…</option>
                  {PURPOSES.map((p) => <option key={p}>{p}</option>)}
                </select>
              </div>
              <div className={field(invalid.config)}>
                <label>Q2. Configuration <span className="req">*</span></label>
                <select value={config} onChange={(e) => setConfig(e.target.value)}>
                  <option value="">Select…</option>
                  {CONFIGS.map((c) => <option key={c}>{c}</option>)}
                </select>
              </div>
            </div>

            <div className="two">
              <div className={field(invalid.budget)}>
                <label>Q3. Budget <span className="req">*</span> <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 10.5 }}>lacs</span></label>
                <div style={{ display: "flex", gap: 6 }}>
                  <input type="number" min="0" placeholder="min" value={budgetMin} onChange={(e) => setBudgetMin(e.target.value)} />
                  <input type="number" min="0" placeholder="max" value={budgetMax} onChange={(e) => setBudgetMax(e.target.value)} />
                </div>
                {bMin > 0 && bMax > 0 && (
                  <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--emerald)", marginTop: 4 }}>
                    ₹{bMin}–{bMax}L · shows to ₹{bMax + 10}L
                  </div>
                )}
              </div>
              <div className="field">
                <label>Q4. Size <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 10.5 }}>sq.ft</span></label>
                <div style={{ display: "flex", gap: 6 }}>
                  <input type="number" min="0" placeholder="min" value={sizeMin} onChange={(e) => setSizeMin(e.target.value)} />
                  <input type="number" min="0" placeholder="max" value={sizeMax} onChange={(e) => setSizeMax(e.target.value)} />
                </div>
              </div>
            </div>

            <div className="field">
              <label>Q5. Micro-markets <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— suggests localities + societies</span></label>
              <AutocompleteChips
                value={micromarkets}
                onChange={onMicromarketsChange}
                placeholder="Search micro-markets…"
                fetcher={async (q) => (await api.searchMicromarkets(q)).items.map((h) => ({ label: h.micro_market, sub: h.city }))}
              />
            </div>

            <div className="field">
              <label>Q6. Preferred localities <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— suggests societies</span></label>
              <AutocompleteChips
                value={localities}
                onChange={onLocalitiesChange}
                suggestions={localitySuggest}
                placeholder="Search localities…"
                fetcher={async (q) => (await api.searchLocalities(q)).items.map((l) => ({ label: l }))}
              />
            </div>

            <div className="field">
              <label>Q7. Shortlisted societies <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— search master list</span></label>
              <AutocompleteChips
                value={societies}
                onChange={setSocieties}
                suggestions={societySuggest}
                placeholder="Search societies…"
                fetcher={async (q) => (await api.searchSocieties(q)).items.map((h) => ({ label: h.society, sub: [h.locality, h.city].filter(Boolean).join(", ") }))}
              />
            </div>

            <div className="field" style={{ marginTop: 12, marginBottom: 0 }}>
              <label>Remark</label>
              <textarea rows={2} value={remark} placeholder="Anything notable from the call" onChange={(e) => setRemark(e.target.value)} />
            </div>

            {showErr && reqInvalid && (
              <div className="mand-flag show"><IconWarn /> Fill all starred (*) fields.</div>
            )}
            {/* ONE button (15 Sep). It saves the answers and nothing else — no callback,
                no stage change. Qualifying and rejecting moved to the Status card's stage
                picker; note that picking "rejected" there records no reason or notes. */}
            <div className="form-actions">
              {lead.stage === "rejected" && (
                <span className="stage lost">Rejected — {lead.reject_reason}</span>
              )}
              <button className="btn green" onClick={saveOnly} disabled={confirm.isPending}>
                {confirm.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </div>

          <LeadHistory id={id} />
        </div>
        <div className="dcol">
          {!mobile && <SavedVisitCard id={id} onEdit={() => setPlanner(true)} booked={isPipeline} />}
          <CallActivityCard leadId={lead.id} />
          {/* Separate from Call activity: that card is the RM's own calls via Bonvoice,
              this one is what Huvo's bot got out of the lead. Both render nothing when
              empty, so a lead with neither shows neither. */}
          <HuvoCallCard leadId={lead.id} />
        </div>
      </div>
    </>
  );
}
