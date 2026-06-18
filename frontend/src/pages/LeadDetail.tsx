/* Lead Detail — source-captured data + the Q1-Q6 call-confirm form (saves to
   POST /v1/leads/:id/confirm). Mirrors the prototype's lead-detail left column. */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  useLead, useConfirmLead, useRejectLead, useMatchPreview, formatPrice,
  useLeadNotes, useAddNote, usePatchSourceData, formatDateTime, useLatestVisit, formatDate, useMarkPriority,
} from "../lib/queries";
import { srcClass, srcLabel, initials } from "../lib/leads";
import { MatchUnit, api } from "../lib/api";
import { useToast } from "../components/Toast";
import { AutocompleteChips, AutocompleteInput } from "../components/Autocomplete";
import { AssignControl } from "../components/AssignControl";
import { WhatsAppIcon } from "../components/icons";
import { waChat } from "../lib/whatsapp";
import { useDebounce } from "../lib/useDebounce";
import { openInMaps } from "../lib/maps";
import { VisitPlanner } from "../features/VisitPlanner";

const PURPOSES = ["Self-use", "Investment"];
const CONFIGS = ["2 BHK", "2.5 BHK", "3 BHK", "3.5 BHK", "4 BHK"];
const OFFICE = ["Yes", "No", "Maybe"];
const PLANS = ["Within 30 days", "1–3 months", "3–6 months", "Just exploring"];

const OFFICE_PITCH_EN = [
  "First, we'll help you understand the market.",
  "We'll give an overview of the city in half an hour.",
  "We'll show on a map how long it takes to travel to different locations.",
  "Areas & options available for you within your budget.",
  "This gives you clarity — then we visit properties.",
  "Advantages / disadvantages if you change your location.",
  "Far better than roaming different properties & wasting 1–2 months on the ground.",
];
const OFFICE_PITCH_HI = [
  "Sabse pehle hum aapko market samjhayenge.",
  "Sheher ka pura overview aadhe ghante mein de denge.",
  "Map pe dikhayenge ki alag-alag locations tak pahunchne mein kitna time lagega.",
  "Aapke budget mein kaunse areas aur options available hain.",
  "Isse aapko clarity milegi — phir properties visit karenge.",
  "Agar aap location change karte hain to uske fayde/nuksan kya honge.",
  "Yeh tareeka 1–2 mahine ground pe ghoom ke waste karne se kaafi behtar hai.",
];

// only one reason for now — preselected (re-add Broker/Budget/Location here later)
const REJECT_REASONS = ["Requirement Mismatch"];

function RejectModal({ id, name, onClose }: { id: string; name: string | null; onClose: () => void }) {
  const reject = useRejectLead(id);
  const toast = useToast();
  const [reason, setReason] = useState(REJECT_REASONS[0]);
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState(false);

  const submit = () => {
    if (!reason || !notes.trim()) { setErr(true); return; }
    reject.mutate({ reason, notes: notes.trim() }, {
      onSuccess: () => { toast("Lead rejected", "blue", "✕"); onClose(); },
      onError: (e: any) => toast(e.message, "gold", "⚠"),
    });
  };

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="mh"><h3>Reject {name}</h3><div className="icon-btn" onClick={onClose}>✕</div></div>
        <div className="mb">
          <div className={"field" + (err && !reason ? " invalid" : "")}>
            <label>Reason for rejection <span className="req">*</span></label>
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              <option value="">Select…</option>
              {REJECT_REASONS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          {reason && (
            <div className={"field" + (err && !notes.trim() ? " invalid" : "")} style={{ marginBottom: 0 }}>
              <label>Notes <span className="req">*</span></label>
              <textarea rows={3} value={notes} placeholder="Why is this lead being rejected?" onChange={(e) => setNotes(e.target.value)} />
            </div>
          )}
          {err && (!reason || !notes.trim()) && <div className="mand-flag show">⚠ A reason and notes are required.</div>}
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" style={{ background: "var(--coral)", color: "#fff" }} onClick={submit} disabled={reject.isPending}>
            {reject.isPending ? "Rejecting…" : "Reject lead"}
          </button>
        </div>
      </div>
    </div>
  );
}

function SourceCard({ lead }: { lead: any }) {
  const patch = usePatchSourceData(lead.id);
  const toast = useToast();
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState({
    city: lead.city || "", society: lead.society || "", budget_band: lead.budget_band || "",
    plan_to_buy: lead.plan_to_buy || "", source_remarks: lead.source_remarks || "",
  });
  useEffect(() => {
    setF({ city: lead.city || "", society: lead.society || "", budget_band: lead.budget_band || "",
      plan_to_buy: lead.plan_to_buy || "", source_remarks: lead.source_remarks || "" });
  }, [lead]);

  const save = () =>
    patch.mutate(f, { onSuccess: () => { toast("Source data updated", "green", "✓"); setEdit(false); }, onError: (e: any) => toast(e.message, "gold", "⚠") });

  const ro = (label: string, val: string | null) => (
    <div className="field"><label>{label}</label><input value={val || "—"} disabled /></div>
  );
  const inp = (label: string, key: keyof typeof f, placeholder = "") => (
    <div className="field"><label>{label}</label>
      <input value={f[key]} placeholder={placeholder} onChange={(e) => setF({ ...f, [key]: e.target.value })} /></div>
  );

  return (
    <div className="card panel-pad meta-card">
      <div className="panel-title" style={{ justifyContent: "space-between" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>Lead data captured from {srcLabel(lead.source)}</span>
        {edit ? (
          <span style={{ display: "flex", gap: 6 }}>
            <button className="btn ghost sm" onClick={() => setEdit(false)}>Cancel</button>
            <button className="btn green sm" onClick={save} disabled={patch.isPending}>{patch.isPending ? "Saving…" : "Save"}</button>
          </span>
        ) : (
          <button className="btn ghost sm" onClick={() => setEdit(true)}>✎ Edit</button>
        )}
      </div>
      {edit ? (
        <>
          <div className="two">{inp("Budget", "budget_band", "e.g. ₹70L – ₹90L")}{inp("City", "city")}</div>
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
          <div className="two">{ro("Budget", lead.budget_band)}{ro("City", lead.city)}</div>
          <div className="two">{ro("Society of interest", lead.society)}{ro("Plan to Buy", lead.plan_to_buy)}</div>
          {lead.preferred_visit_day && ro("Preferred visit day (from ad)", lead.preferred_visit_day)}
          {lead.source_remarks && ro("Source remarks", lead.source_remarks)}
        </>
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
    addNote.mutate(t, { onSuccess: () => setText(""), onError: (e: any) => toast(e.message, "gold", "⚠") });
  };
  return (
    <div className="card panel-pad">
      <div className="panel-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>{" "}
        Conversation &amp; remarks
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 9, marginBottom: 12 }}>
        {isLoading ? (
          <div className="empty" style={{ padding: 14 }}>Loading…</div>
        ) : !data?.items.length ? (
          <div className="empty" style={{ padding: 14, fontSize: 12 }}>No remarks yet — start the thread below.</div>
        ) : (
          data.items.map((n, i) => (
            <div key={n.id || `seed-${i}`} style={{
              background: n.source === "remarks" ? "var(--panel-2)" : "var(--blue-soft)",
              border: "1px solid var(--line)", borderRadius: 10, padding: "9px 11px",
            }}>
              <div style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.45 }}>{n.body}</div>
              <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 4, fontFamily: "'Spline Sans Mono'" }}>
                {n.author || "—"}{n.created_at ? ` · ${formatDateTime(n.created_at)}` : ""}
                {n.source === "remarks" && " · imported"}
              </div>
            </div>
          ))
        )}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={text}
          placeholder="Add a remark…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          style={{ flex: 1 }}
        />
        <button className="btn primary sm" onClick={send} disabled={addNote.isPending || !text.trim()}>Send</button>
      </div>
    </div>
  );
}

function MatchRow({ u, isSupply, leadId, leadPhone, leadName }: { u: MatchUnit; isSupply: boolean; leadId: string; leadPhone: string | null; leadName: string | null }) {
  const [open, setOpen] = useState(false);
  const toast = useToast();
  const markPriority = useMarkPriority(leadId);
  const onMark = (e: React.MouseEvent) => {
    e.stopPropagation();
    markPriority.mutate(
      { uid: u.id, priority: true },
      {
        onSuccess: () => toast("Marked as Direct Demand priority", "green", "★"),
        onError: (err) => toast(err instanceof Error ? err.message : "Could not mark priority", "gold", "⚠"),
      },
    );
  };
  const detail: [string, string | null | undefined][] = [
    ["Society", u.society],
    ["City", u.city],
    ["Configuration", u.configuration],
    ["Super area", u.area_sqft != null ? `${u.area_sqft.toLocaleString("en-IN")} sq.ft` : null],
    ["Ask price", formatPrice(u.price_lacs, u.price_text)],
    isSupply ? ["Stage", u.stage] : ["Status", u.status],
  ];
  const share = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!leadPhone) { toast("No phone number for this lead", "gold", "⚠"); return; }
    const text = `Hi ${leadName || ""}, sharing a property that matches your requirement:\n\n🏠 ${u.name}\n📍 ${[u.locality, u.city].filter(Boolean).join(", ")}\n${formatPrice(u.price_lacs, u.price_text)} · ${u.configuration || ""}`
      + (u.image_url ? `\n${u.image_url}` : "");
    waChat(leadPhone, text);
  };
  return (
    <div className={"opt" + (open ? " open" : "")}>
      <div className="opt-row" onClick={() => setOpen(!open)}>
        {!isSupply && (
          <div
            className="opt-thumb"
            style={u.image_url
              ? { backgroundImage: `url('${u.image_url}')` }
              : { background: "linear-gradient(135deg,#e4e9f1,#d3dbe8)", display: "grid", placeItems: "center", fontSize: 16 }}
          >
            {!u.image_url && "🏠"}
          </div>
        )}
        <div className="opt-info">
          <div className="opt-name">
            {u.name || "—"} <span className="match-mini">{u.score}%</span>
            {isSupply && u.priority && (
              <span className="match-mini" style={{ background: "var(--gold-soft)", color: "var(--gold)", marginLeft: 4 }}>★ Priority</span>
            )}
          </div>
          <div className="opt-meta">
            {u.configuration || "—"} · {u.area_sqft != null ? `${u.area_sqft.toLocaleString("en-IN")} sq.ft` : "—"} ·{" "}
            <b style={{ color: "var(--ink-2)" }}>{formatPrice(u.price_lacs, u.price_text)}</b>
          </div>
        </div>
        <button className="wa-ico" title="Share on WhatsApp" onClick={share}><WhatsAppIcon /></button>
        <svg className="opt-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </div>
      <div className="opt-detail">
        {u.matched_on.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 10 }}>
            {u.matched_on.map((r) => (
              <span key={r} className="match-mini" style={{ background: "var(--emerald-soft)", color: "#06694b" }}>{r}</span>
            ))}
          </div>
        )}
        <div className="opt-dl">
          {detail.map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <div className="opt-dt">{k}</div>
              <div className="opt-dd">{v || "—"}</div>
            </div>
          ))}
        </div>
        {isSupply && (
          <div style={{ marginTop: 12 }}>
            {u.priority ? (
              <span className="btn sm" style={{ background: "var(--gold-soft)", color: "var(--gold)", cursor: "default", fontWeight: 700 }}>
                ★ Marked Priority
              </span>
            ) : (
              <button
                className="btn sm"
                style={{ background: "var(--gold)", color: "#fff", boxShadow: "0 6px 16px -8px var(--gold)" }}
                onClick={onMark}
                disabled={markPriority.isPending}
              >
                {markPriority.isPending ? "Marking…" : "★ Mark as Priority"}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SavedVisitCard({ id, onEdit }: { id: string; onEdit: () => void }) {
  const { data, isLoading } = useLatestVisit(id);
  const plan = data?.plan;
  if (isLoading || !plan) return null;
  return (
    <div className="card panel-pad">
      <div className="panel-title" style={{ justifyContent: "space-between" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>📅 Planned site visits</span>
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

function MatchPanel({ title, tag, units, loading, leadId, leadPhone, leadName }: { title: string; tag: string; units: MatchUnit[]; loading: boolean; leadId: string; leadPhone: string | null; leadName: string | null }) {
  return (
    <div className="card panel-pad">
      <div className="panel-title" style={{ justifyContent: "space-between" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {title}
          <span title="Updates live as you edit" style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 9.5, fontWeight: 700, color: "var(--emerald)", letterSpacing: ".04em" }}>
            <span className="tat" style={{ padding: 0, background: "none" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--emerald)", display: "inline-block", animation: loading ? "pulse 1s infinite" : undefined }} />
            </span>
            LIVE
          </span>
        </span>
        <span style={{ fontSize: 10, fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>{tag}</span>
      </div>
      {units.length === 0 ? (
        <div className="empty" style={{ padding: 16 }}>{loading ? "Matching…" : "No matches yet — add budget, config or a society to surface more."}</div>
      ) : (
        units.map((u) => <MatchRow key={u.id} u={u} isSupply={tag.includes("SUPPLY")} leadId={leadId} leadPhone={leadPhone} leadName={leadName} />)
      )}
    </div>
  );
}

export default function LeadDetail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { data: lead, isLoading } = useLead(id);
  const confirm = useConfirmLead(id);
  const [planner, setPlanner] = useState(false);
  const [rejecting, setRejecting] = useState(false);

  const [purpose, setPurpose] = useState("");
  const [budgetMin, setBudgetMin] = useState("");
  const [budgetMax, setBudgetMax] = useState("");
  const [config, setConfig] = useState("");
  const [sizeMin, setSizeMin] = useState("");
  const [sizeMax, setSizeMax] = useState("");
  const [micromarkets, setMicromarkets] = useState<string[]>([]);
  const [societies, setSocieties] = useState<string[]>([]);
  const [localities, setLocalities] = useState<string[]>([]);
  const [office, setOffice] = useState("");
  const [officeDate, setOfficeDate] = useState("");
  const [remark, setRemark] = useState("");
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
    setOffice(c?.office_willing || "");
    setOfficeDate(c?.office_preferred_date || "");
    setRemark(c?.remark || "");
  }, [lead]);

  // cascade: a micro-market fills its localities AND their societies; a locality fills its societies
  const addSocietiesFor = async (locs: string[]) => {
    const lists = await Promise.all(locs.map((l) => api.societiesByLocality(l).then((r) => r.items).catch(() => [])));
    const socs = lists.flat();
    if (socs.length) setSocieties((prev) => Array.from(new Set([...prev, ...socs])));
  };
  const onMicromarketsChange = (next: string[]) => {
    const added = next.filter((m) => !micromarkets.includes(m));
    setMicromarkets(next);
    added.forEach(async (mm) => {
      try {
        const locs = (await api.localitiesByMicromarket(mm)).items;
        setLocalities((prev) => Array.from(new Set([...prev, ...locs])));
        addSocietiesFor(locs); // cascade the second level too
      } catch { /* ignore */ }
    });
  };
  const onLocalitiesChange = (next: string[]) => {
    const added = next.filter((l) => !localities.includes(l));
    setLocalities(next);
    addSocietiesFor(added);
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
  const debouncedReq = useDebounce(reqKey, 350);
  const { data: matches, isFetching: matchesLoading } = useMatchPreview(JSON.parse(debouncedReq));

  if (isLoading) return <div className="card"><div className="empty" style={{ padding: 40 }}>Loading lead…</div></div>;
  if (!lead) return <div className="card"><div className="empty" style={{ padding: 40 }}>Lead not found.</div></div>;

  const invalid = { purpose: !purpose, budget: !(bMin > 0 && bMax > 0 && bMax >= bMin), config: !config, office: !office };
  const anyInvalid = invalid.purpose || invalid.budget || invalid.config || invalid.office;

  const save = () => {
    if (anyInvalid) {
      setShowErr(true);
      toast("Please fill the required (*) fields", "gold", "⚠");
      return;
    }
    confirm.mutate(
      {
        purpose,
        budget_min_lacs: bMin,
        budget_max_lacs: bMax,
        configuration: config,
        size_min_sqft: sMin > 0 ? sMin : null,
        size_max_sqft: sMax > 0 ? sMax : null,
        preferred_micromarkets: micromarkets,
        shortlisted_societies: societies,
        preferred_localities: localities,
        office_willing: office,
        office_preferred_date: office === "Yes" || office === "Maybe" ? officeDate || null : null,
        remark: remark || null,
      },
      {
        onSuccess: () => toast("Lead confirmed & qualified", "green", "✓"),
        onError: (e) => toast(e.message, "gold", "⚠"),
      }
    );
  };

  const field = (bad: boolean) => "field" + (showErr && bad ? " invalid" : "");

  return (
    <>
      <div className="back" onClick={() => nav(-1)}>← Back</div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 14, marginBottom: 18 }}>
        <div className="lead-head">
          <div className="av">{initials(lead.name)}</div>
          <div>
            <h2>{lead.name}{lead.is_test && <span className="bucket-tag" style={{ marginLeft: 8, verticalAlign: "middle" }}>TEST</span>}</h2>
            <div className="meta" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              {lead.phone}
              <span className={`src ${srcClass(lead.source)}`}>{srcLabel(lead.source)}</span>
              <span style={{ color: "var(--muted)" }}>Assigned:</span>
              <AssignControl leadId={lead.id} assignedTo={lead.assigned_to} />
              {lead.confirmed && <span className="stage contacted">Qualified</span>}
            </div>
          </div>
        </div>
        <div className="lead-actions">
          <button className="btn ghost" onClick={() => setPlanner(true)}>📅 Plan visits</button>
          <button className="btn wa" onClick={() => lead.phone ? waChat(lead.phone, `Hi ${lead.name || ""}, this is Openhouse Direct Demand.`) : toast("No phone number", "gold", "⚠")}>
            <WhatsAppIcon /> WhatsApp
          </button>
        </div>
      </div>
      {planner && <VisitPlanner leadId={id} leadName={lead.name} leadCity={lead.city} onClose={() => setPlanner(false)} />}
      {rejecting && <RejectModal id={id} name={lead.name} onClose={() => setRejecting(false)} />}

      <div className="detail-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {/* SOURCE-CAPTURED — editable */}
          <SourceCard lead={lead} />

          {/* CONVERSATION / REMARKS THREAD */}
          <NotesThread id={id} />


          {/* CONFIRMED call form */}
          <div className="card panel-pad compact-form">
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
              <label>Q5. Micro-markets <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— auto-fills localities + societies</span></label>
              <AutocompleteChips
                value={micromarkets}
                onChange={onMicromarketsChange}
                placeholder="Search micro-markets…"
                fetcher={async (q) => (await api.searchMicromarkets(q)).items.map((h) => ({ label: h.micro_market, sub: h.city }))}
              />
            </div>

            <div className="field">
              <label>Q6. Preferred localities <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— auto-fills societies</span></label>
              <AutocompleteChips
                value={localities}
                onChange={onLocalitiesChange}
                placeholder="Search localities…"
                fetcher={async (q) => (await api.searchLocalities(q)).items.map((l) => ({ label: l }))}
              />
            </div>

            <div className="field">
              <label>Q7. Shortlisted societies <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— search master list</span></label>
              <AutocompleteChips
                value={societies}
                onChange={setSocieties}
                placeholder="Search societies…"
                fetcher={async (q) => (await api.searchSocieties(q)).items.map((h) => ({ label: h.society, sub: [h.locality, h.city].filter(Boolean).join(", ") }))}
              />
            </div>

            <div className="two">
              <div className={field(invalid.office)}>
                <label>Q8. Willing to come to office? <span className="req">*</span></label>
                <select value={office} onChange={(e) => setOffice(e.target.value)}>
                  <option value="">Select…</option>
                  {OFFICE.map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
              {(office === "Yes" || office === "Maybe") ? (
                <div className="field">
                  <label>Preferred date</label>
                  <input type="date" value={officeDate} onChange={(e) => setOfficeDate(e.target.value)} />
                </div>
              ) : <div />}
            </div>

            {(office === "No" || office === "Maybe") && (
              <div className="office-pitch">
                <div className="op-head">💬 Pitch the office visit — why it helps</div>
                <ul className="op-list">{OFFICE_PITCH_EN.map((x, i) => <li key={i}>{x}</li>)}</ul>
                <div className="op-sub">Hinglish</div>
                <ul className="op-list hi">{OFFICE_PITCH_HI.map((x, i) => <li key={i}>{x}</li>)}</ul>
              </div>
            )}

            <div className="field" style={{ marginTop: 12, marginBottom: 0 }}>
              <label>Remark</label>
              <textarea rows={2} value={remark} placeholder="Anything notable from the call" onChange={(e) => setRemark(e.target.value)} />
            </div>

            {showErr && anyInvalid && <div className="mand-flag show">⚠ Please fill all starred (*) fields to confirm the lead.</div>}
            <div style={{ marginTop: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              {lead.stage === "rejected" ? (
                <span className="stage lost">Rejected — {lead.reject_reason}</span>
              ) : (
                <button className="btn" style={{ background: "var(--coral)", color: "#fff" }} onClick={() => setRejecting(true)}>
                  ✕ Reject lead
                </button>
              )}
              <button className="btn green" onClick={save} disabled={confirm.isPending}>
                {confirm.isPending ? "Saving…" : lead.confirmed ? "Update confirmed data" : "Confirm & qualify lead"}
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT column — saved visit plan + live matched inventory + supply */}
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <SavedVisitCard id={id} onEdit={() => setPlanner(true)} />
          <MatchPanel title="Best matches from inventory" tag="ACQUIRED PROPERTY" units={matches?.inventory ?? []} loading={matchesLoading} leadId={lead.id} leadPhone={lead.phone} leadName={lead.name} />
          <MatchPanel title="From supply pipeline" tag="SUPPLY CLOSURE TRACKER" units={matches?.supply ?? []} loading={matchesLoading} leadId={lead.id} leadPhone={lead.phone} leadName={lead.name} />
        </div>
      </div>
    </>
  );
}
