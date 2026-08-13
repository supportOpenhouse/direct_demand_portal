/* Huvo Call Log — every call Huvo's bot completed, with the analytics it produced.

   Laid out like the Bonvoice log, but filtered on different things. That page
   describes a telephony leg — who dialled, did it connect, how long. This one
   describes what was said, so the useful axes are the outcome, whether they're
   interested, and whether the call is attached to a lead at all.

   That last filter is the point of the page today: a third of these calls are for
   numbers with no lead, and "Create lead" turns one into a real lead and back-links
   every call from that number in the same click. */
import { useState } from "react";
import { Link } from "react-router-dom";
import { HuvoCall, DURATION_OPTIONS } from "../lib/api";
import { CITIES } from "../lib/leads";
import {
  useHuvoCalls, useHuvoCall, useHuvoCallFilters, useCreateHuvoLead,
  useBulkCreateHuvoLeads, useSocietiesByCity, formatDateTime,
} from "../lib/queries";
import { FilterSelect } from "../components/Filters";
import { useToast } from "../components/Toast";
import { useDebounce } from "../lib/useDebounce";
import RecordingPlayer from "../components/RecordingPlayer";

const PAGE = 50;
const LINKED_OPTIONS = [
  { value: "linked", label: "Has a lead" },
  { value: "unlinked", label: "No lead yet" },
];

/* Outcomes carry weight — a qualified call and a wrong number shouldn't look alike in
   a list you're scanning. Grouped rather than coloured per value: sixteen colours is
   noise, three tiers is information. */
const GOOD = new Set(["qualified", "site_visit_scheduled", "home_visit_scheduled",
                      "online_meeting_scheduled", "need_details_whatsapp"]);
const DEAD = new Set(["not_interested", "unqualified", "already_booked_elsewhere",
                      "another_location", "wrong_number", "duplicate_lead"]);

function outcomeStyle(outcome: string | null) {
  if (!outcome) return { background: "var(--panel-2)", color: "var(--muted)" };
  if (GOOD.has(outcome)) return { background: "var(--emerald-soft)", color: "#06694b" };
  if (DEAD.has(outcome)) return { background: "var(--coral-soft)", color: "var(--coral)" };
  return { background: "var(--amber-soft)", color: "var(--amber)" };  // retryable
}

const pretty = (v: string) => v.replace(/_/g, " ");
const mmss = (s: number | null) =>
  s == null ? "—" : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/* Create lead from a call — the WhatsApp modal's twin. Phone is fixed: it's what ties
   the new lead to the calls being linked. */
function CreateLeadModal(
  { call, onClose }: { call: HuvoCall; onClose: () => void },
) {
  const create = useCreateHuvoLead();
  const toast = useToast();
  const [form, setForm] = useState({ name: call.caller_name || "", city: "", society: "" });
  const societies = useSocietiesByCity(form.city);
  const societyOptions = societies.data?.items ?? [];

  const submit = () => {
    if (!form.name.trim() || create.isPending) return;
    create.mutate(
      { phone: call.from_number || "", name: form.name.trim(),
        city: form.city.trim(), society: form.society.trim() },
      {
        onSuccess: (d) => {
          toast(d.calls_linked > 1
            ? `Lead created · ${d.calls_linked} calls linked`
            : "Lead created", "green", "✓");
          onClose();
        },
        onError: (e: any) => toast(e.message, "gold", "⚠"),
      },
    );
  };

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="mh">
          <h3>Create lead from call</h3>
          <div className="icon-btn" onClick={onClose}>✕</div>
        </div>
        <div className="mb">
          <div className="field">
            <label>Name <span className="req">*</span></label>
            <input value={form.name} autoFocus placeholder="Full name"
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </div>
          <div className="field">
            <label>Phone</label>
            {/* the call's number — editing it would detach the lead from these calls */}
            <input value={call.from_number || ""} readOnly
              style={{ background: "var(--panel-2)", color: "var(--muted)" }} />
          </div>
          <div className="field">
            <label>City</label>
            <select value={form.city}
              // changing city invalidates the society — it may not exist there
              onChange={(e) => setForm((f) => ({ ...f, city: e.target.value, society: "" }))}>
              <option value="">Choose city (optional)</option>
              {CITIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Society</label>
            <select value={form.society} disabled={!form.city}
              onChange={(e) => setForm((f) => ({ ...f, society: e.target.value }))}>
              <option value="">
                {!form.city ? "Choose a city first"
                  : societies.isLoading ? "Loading…"
                  : societyOptions.length ? "Choose society (optional)"
                  : "No societies found for this city"}
              </option>
              {societyOptions.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          {/* What Huvo already learned on the call — saves re-reading the row behind
              the modal to decide whether this lead is worth creating. */}
          {call.summary && (
            <div className="note" style={{ marginTop: 12, fontSize: 12, maxHeight: 110, overflow: "auto" }}>
              {call.summary}
            </div>
          )}
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn green" onClick={submit}
            disabled={create.isPending || !form.name.trim()}>
            {create.isPending ? "Creating…" : "Create lead"}
          </button>
        </div>
      </div>
    </div>
  );
}


/* One call, everything we hold about it.

   The table shows eight columns; a call carries about thirty fields. Nine of Huvo's
   analytics values have no database column at all and live only inside `payload`, so
   this reads them from there rather than from the row the table already has. */
function Field({ label, value }: { label: string; value: unknown }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className="hv-field">
      <div className="hv-field-l">{label}</div>
      <div className={"hv-field-v" + (empty ? " muted" : "")}>
        {empty ? "—" : String(value)}
      </div>
    </div>
  );
}

function CallDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const { data: c, isLoading } = useHuvoCall(id);
  const [raw, setRaw] = useState(false);
  const a = (c?.payload?.analytics_data ?? {}) as Record<string, unknown>;
  const extra = c?.payload?._import?.extra ?? {};

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal hv-detail" onClick={(e) => e.stopPropagation()}>
        <div className="mh">
          <h3>{c?.caller_name || "Call detail"}
            {c?.from_number &&
              <span className="hv-detail-num">{c.from_number}</span>}
          </h3>
          <div className="icon-btn" onClick={onClose}>✕</div>
        </div>
        <div className="mb">
          {isLoading || !c ? (
            <div className="empty" style={{ padding: 30 }}>Loading…</div>
          ) : (
            <>
              <div className="hv-sec">The call</div>
              <div className="hv-grid">
                <Field label="Outcome" value={c.call_outcome && pretty(c.call_outcome)} />
                <Field label="Interested" value={c.is_interested} />
                <Field label="RSVP" value={c.rsvp_status && pretty(c.rsvp_status)} />
                <Field label="Lead score" value={c.lead_score} />
                <Field label="Duration" value={mmss(c.duration_sec)} />
                <Field label="Answered by" value={a.callback_owner} />
                <Field label="Started" value={formatDateTime(c.started_at)} />
                <Field label="Ended" value={formatDateTime(c.ended_at)} />
                <Field label="Received" value={formatDateTime(c.received_at)} />
              </div>

              <div className="hv-sec">What they want</div>
              <div className="hv-grid">
                <Field label="Project" value={a.project_name} />
                <Field label="Location" value={a.location} />
                <Field label="Property type" value={a.type_of_property} />
                <Field label="Purpose" value={a.purpose} />
                {/* both: the crores string is what Huvo said, the lacs is ours */}
                <Field label="Budget (as stated)" value={a.budget_crores} />
                <Field label="Budget (lacs)" value={c.budget_lacs} />
                <Field label="Why interested" value={a.interest_reason} />
              </div>

              <div className="hv-sec">Scheduling</div>
              <div className="hv-grid">
                <Field label="Site visit" value={a.site_visit_schedule} />
                <Field label="Outcome schedule" value={a.call_outcome_schedule} />
                <Field label="Follow-up (as said)" value={a.follow_up_time} />
                {/* Usually blank: Huvo sends prose like "two o'clock", and a follow-up
                    is only stored when a real ISO timestamp came with it. */}
                <Field label="Follow-up (parsed)" value={formatDateTime(c.follow_up_at)} />
              </div>

              {c.summary && <>
                <div className="hv-sec">Summary</div>
                <p className="hv-summary">{c.summary}</p>
              </>}

              {c.recording_url && <>
                <div className="hv-sec">Recording</div>
                <RecordingPlayer src={c.recording_url} />
              </>}

              {Object.keys(extra).length > 0 && <>
                {/* Columns from the CSV export that aren't in Huvo's webhook schema —
                    kept on import rather than dropped. */}
                <div className="hv-sec">From the import</div>
                <div className="hv-grid">
                  {Object.entries(extra).map(([k, v]) => <Field key={k} label={k} value={v} />)}
                </div>
              </>}

              <div className="hv-sec">
                Raw
                <button className="btn ghost sm" style={{ marginLeft: 8 }}
                  onClick={() => setRaw((v) => !v)}>{raw ? "Hide" : "Show"}</button>
              </div>
              {raw && <pre className="hv-raw">{JSON.stringify(c.payload, null, 2)}</pre>}
              <div className="hv-key">{c.dedupe_key}</div>
            </>
          )}
        </div>
        <div className="mf">
          {c?.lead_id
            ? <Link className="btn ghost" to={`/leads/${c.lead_id}`}>Open lead ↗</Link>
            : <span style={{ fontSize: 12, color: "var(--muted)" }}>No lead for this number yet</span>}
          <button className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

export default function HuvoCalls() {
  const [q, setQ] = useState("");
  const [outcome, setOutcome] = useState("");
  const [interested, setInterested] = useState("");
  const [linked, setLinked] = useState("");
  const [dur, setDur] = useState("");
  const [page, setPage] = useState(0);
  const [creating, setCreating] = useState<HuvoCall | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  // Bulk mode is opt-in so the table stays a reading surface by default; checkboxes
  // on every row would make scanning it harder for the commoner case.
  const [bulk, setBulk] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const bulkCreate = useBulkCreateHuvoLeads();
  const toast = useToast();
  const dq = useDebounce(q, 300);

  const filters = useHuvoCallFilters().data;
  const { data, isLoading, isFetching } = useHuvoCalls({
    q: dq || undefined,
    outcome: outcome || undefined,
    interested: interested || undefined,
    linked: linked || undefined,
    duration: dur || undefined,
    limit: PAGE,
    offset: page * PAGE,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  // Undefined until the backend carrying these counts is deployed. Rendering "0
  // unique leads" for 1,603 calls is worse than rendering nothing at all.
  const uniqueLeads = data?.unique_leads;
  const unlinkedTotal = data?.unlinked_unique;

  /* Selection is by phone number, not row id: several calls can share a number and
     they'd all produce the same one lead. Rows that already have a lead aren't
     selectable — there'd be nothing to create. */
  const convertible = Array.from(new Set(
    items.filter((c) => !c.lead_id && c.from_number).map((c) => c.from_number as string)));
  const toggle = (phone: string) => setPicked((prev) => {
    const next = new Set(prev);
    next.has(phone) ? next.delete(phone) : next.add(phone);
    return next;
  });
  const exitBulk = () => { setBulk(false); setPicked(new Set()); };
  /* Everything unlinked under the current filters, not just this page. Falls back to
     the page's own count on an older backend that doesn't send the total. */
  const bulkTarget = unlinkedTotal ?? convertible.length;
  const runBulk = () => bulkCreate.mutate(
    // A selection means those exactly; no selection means "all of them", resolved
    // server-side from the filters — 845 numbers can't travel in a request body.
    picked.size
      ? { phones: Array.from(picked) }
      : { all_matching: true, q: dq || undefined, outcome: outcome || undefined,
          interested: interested || undefined, duration: dur || undefined },
    {
    onSuccess: (d) => {
      const skipped = d.requested - d.created;
      toast(`${d.created} lead${d.created === 1 ? "" : "s"} created`
            + (skipped ? ` · ${skipped} already existed` : "")
            + ` · ${d.calls_linked} calls linked`, "green", "✓");
      exitBulk();
    },
    onError: (e: any) => toast(e.message, "gold", "⚠"),
  });
  const start = total === 0 ? 0 : page * PAGE + 1;
  const end = Math.min(total, (page + 1) * PAGE);
  const reset = (fn: () => void) => { fn(); setPage(0); };
  const anyFilter = q || outcome || interested || linked || dur;

  return (
    <>
      <div className="section-head hv-head">
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{total.toLocaleString("en-IN")}</b> calls
          {/* Huvo calls the same person more than once, so the call count alone
              overstates how many people are actually in this list. */}
          {uniqueLeads !== undefined && <>
            {" · "}
            <b style={{ color: "var(--ink-2)" }}>{uniqueLeads.toLocaleString("en-IN")}</b> unique leads
          </>}
          {isFetching ? " · updating…" : ""}
        </p>
        <div className="hv-filters">
          <FilterSelect label="Outcome" value={outcome} width={190}
            options={(filters?.outcomes ?? []).map((o: string) => ({ value: o, label: pretty(o) }))}
            onChange={(v) => reset(() => setOutcome(v))} />
          <FilterSelect label="Interested" value={interested} width={140}
            options={filters?.interest ?? []} onChange={(v) => reset(() => setInterested(v))} />
          <FilterSelect label="Lead" value={linked} options={LINKED_OPTIONS} width={150}
            onChange={(v) => reset(() => setLinked(v))} />
          <FilterSelect label="Duration" value={dur} options={DURATION_OPTIONS} width={140}
            onChange={(v) => reset(() => setDur(v))} />
          <div className="field hv-search">
            <input value={q} placeholder="Search number / name / summary…"
              onChange={(e) => reset(() => setQ(e.target.value))} />
          </div>
          {anyFilter && (
            <button className="btn ghost sm" onClick={() => {
              setQ(""); setOutcome(""); setInterested(""); setLinked(""); setDur(""); setPage(0);
            }}>Clear</button>
          )}
          <span style={{ width: 1, height: 22, background: "var(--line)" }} />
          {bulk ? (
            <>
              <button className="btn ghost sm" onClick={() =>
                setPicked(picked.size === convertible.length ? new Set() : new Set(convertible))}>
                {picked.size === convertible.length && convertible.length > 0
                  ? "Clear all" : `Select page (${convertible.length})`}
              </button>
              <button className="btn primary sm" disabled={!bulkTarget || bulkCreate.isPending}
                onClick={runBulk}
                title={picked.size ? "" : "Nothing ticked — creates leads for every unlinked call matching the filters"}>
                {bulkCreate.isPending ? "Creating…"
                  : `Create ${(picked.size || bulkTarget).toLocaleString("en-IN")} lead${(picked.size || bulkTarget) === 1 ? "" : "s"}`}
              </button>
              <button className="btn ghost sm" onClick={exitBulk}>Cancel</button>
            </>
          ) : (
            <button className="btn sm" onClick={() => setBulk(true)} disabled={!bulkTarget}
              title={bulkTarget
                ? "Turn unlinked calls into leads in bulk"
                : "Every call matching these filters already has a lead"}>
              Create leads ({bulkTarget.toLocaleString("en-IN")})
            </button>
          )}
        </div>
      </div>

      <div className="card panel-pad">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {bulk && <th style={{ width: 34 }} />}
                <th style={{ width: 150 }}>When</th>
                <th style={{ width: 150 }}>Caller</th>
                <th style={{ width: 170 }}>Outcome</th>
                <th style={{ width: 60 }}>Score</th>
                <th>Summary</th>
                <th style={{ width: 70 }}>Duration</th>
                <th style={{ width: 110 }}>Recording</th>
                <th style={{ width: 150 }}>Lead</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={bulk ? 9 : 8}><div className="empty" style={{ padding: 24 }}>Loading calls…</div></td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={bulk ? 9 : 8}><div className="empty" style={{ padding: 24 }}>
                  {anyFilter ? "No calls match these filters." : "No Huvo calls yet."}
                </div></td></tr>
              ) : (
                items.map((c) => (
                  <tr key={c.id} className="hv-row" onClick={() => setOpenId(c.id)}>
                    {bulk && (
                      <td onClick={(e) => e.stopPropagation()}>
                        {/* keyed by number: two calls from one person are one lead */}
                        {!c.lead_id && c.from_number ? (
                          <input type="checkbox" checked={picked.has(c.from_number)}
                            onChange={() => toggle(c.from_number as string)} />
                        ) : null}
                      </td>
                    )}
                    <td style={{ fontSize: 12, whiteSpace: "nowrap", fontFamily: "'Spline Sans Mono'" }}>
                      {formatDateTime(c.started_at) || formatDateTime(c.received_at) || "—"}
                    </td>
                    <td style={{ fontSize: 12.5 }}>
                      <div>{c.caller_name || <span style={{ color: "var(--muted)" }}>—</span>}</div>
                      <div style={{ fontSize: 11.5, color: "var(--muted)", fontFamily: "'Spline Sans Mono'" }}>
                        {c.from_number || ""}
                      </div>
                    </td>
                    <td style={{ fontSize: 12.5 }}>
                      <span className="cfg-chip" style={outcomeStyle(c.call_outcome)}>
                        {c.call_outcome ? pretty(c.call_outcome) : "no call"}
                      </span>
                      {c.is_interested === "yes" &&
                        <span style={{ color: "var(--emerald)", fontSize: 11.5, marginLeft: 5 }}>★</span>}
                    </td>
                    <td style={{ fontSize: 12, fontFamily: "'Spline Sans Mono'" }}>
                      {c.lead_score ?? "—"}
                    </td>
                    <td style={{ fontSize: 12, color: "var(--ink-2)", maxWidth: 420 }}>
                      {/* full text on hover — the summary is the most useful column and
                          also far too long to show whole */}
                      <div title={c.summary || ""} style={{
                        display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}>
                        {c.summary || "—"}
                      </div>
                    </td>
                    <td style={{ fontSize: 12, fontFamily: "'Spline Sans Mono'" }}>{mmss(c.duration_sec)}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {c.recording_url
                        ? <RecordingPlayer src={c.recording_url} />
                        : <span style={{ color: "var(--muted)" }}>—</span>}
                    </td>
                    <td style={{ fontSize: 12.5 }} onClick={(e) => e.stopPropagation()}>
                      {c.lead_id ? (
                        <Link className="lead-link" to={`/leads/${c.lead_id}`}>
                          {c.lead_name || "View lead"}
                        </Link>
                      ) : c.from_number ? (
                        <button className="btn ghost sm" onClick={() => setCreating(c)}>
                          + Create lead
                        </button>
                      ) : (
                        // no number to key a lead on — nothing to create
                        <span style={{ color: "var(--muted)" }}>—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
          <span style={{ fontSize: 12, color: "var(--muted)" }}>
            {total > 0 ? `${start}–${end} of ${total.toLocaleString("en-IN")}` : "—"}
          </span>
          <span style={{ display: "flex", gap: 6 }}>
            <button className="btn ghost sm" disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}>← Prev</button>
            <button className="btn ghost sm" disabled={end >= total}
              onClick={() => setPage((p) => p + 1)}>Next →</button>
          </span>
        </div>
      </div>

      {creating && <CreateLeadModal call={creating} onClose={() => setCreating(null)} />}
      {openId && <CallDetail id={openId} onClose={() => setOpenId(null)} />}
    </>
  );
}
