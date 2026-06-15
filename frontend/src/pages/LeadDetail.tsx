/* Lead Detail — source-captured data + the Q1-Q6 call-confirm form (saves to
   POST /v1/leads/:id/confirm). Mirrors the prototype's lead-detail left column. */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  useLead, useConfirmLead, useLeadMatches, formatPrice,
  useLeadNotes, useAddNote, usePatchSourceData, formatDateTime,
} from "../lib/queries";
import { srcClass, srcLabel, initials } from "../lib/leads";
import { MatchUnit, api } from "../lib/api";
import { useToast } from "../components/Toast";
import { AutocompleteChips } from "../components/Autocomplete";

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
          <div className="two">
            {inp("Society of interest", "society")}
            <div className="field"><label>Plan to Buy</label>
              <select value={f.plan_to_buy} onChange={(e) => setF({ ...f, plan_to_buy: e.target.value })}>
                <option value="">Select…</option>{PLANS.map((p) => <option key={p}>{p}</option>)}
              </select></div>
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

function MatchRow({ u, isSupply }: { u: MatchUnit; isSupply: boolean }) {
  const [open, setOpen] = useState(false);
  const detail: [string, string | null | undefined][] = [
    ["Society", u.society],
    ["City", u.city],
    ["Configuration", u.configuration],
    ["Super area", u.area_sqft != null ? `${u.area_sqft.toLocaleString("en-IN")} sq.ft` : null],
    ["Ask price", formatPrice(u.price_lacs, u.price_text)],
    isSupply ? ["Stage", u.stage] : ["Status", u.status],
    ["Matched on", u.matched_on.join(" + ")],
  ];
  return (
    <div className={"opt" + (open ? " open" : "")}>
      <div className="opt-row" onClick={() => setOpen(!open)}>
        <div className="opt-info">
          <div className="opt-name">
            {u.name || "—"} <span className="match-mini">{u.score}%</span>
          </div>
          <div className="opt-meta">
            {u.configuration || "—"} · {u.area_sqft != null ? `${u.area_sqft.toLocaleString("en-IN")} sq.ft` : "—"} ·{" "}
            <b style={{ color: "var(--ink-2)" }}>{formatPrice(u.price_lacs, u.price_text)}</b>
          </div>
          {u.matched_on.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 5 }}>
              {u.matched_on.map((r) => (
                <span key={r} className="match-mini" style={{ background: "var(--emerald-soft)", color: "#06694b" }}>{r}</span>
              ))}
            </div>
          )}
        </div>
        <svg className="opt-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </div>
      <div className="opt-detail">
        <div className="opt-dl">
          {detail.map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <div className="opt-dt">{k}</div>
              <div className="opt-dd">{v || "—"}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MatchPanel({ title, tag, units, loading }: { title: string; tag: string; units: MatchUnit[]; loading: boolean; }) {
  return (
    <div className="card panel-pad">
      <div className="panel-title" style={{ justifyContent: "space-between" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>{title}</span>
        <span style={{ fontSize: 10, fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>{tag}</span>
      </div>
      {loading ? (
        <div className="empty" style={{ padding: 16 }}>Matching…</div>
      ) : units.length === 0 ? (
        <div className="empty" style={{ padding: 16 }}>No matches yet — confirm budget &amp; config to surface more.</div>
      ) : (
        units.map((u) => <MatchRow key={u.id} u={u} isSupply={tag.includes("SUPPLY")} />)
      )}
    </div>
  );
}

export default function LeadDetail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { data: lead, isLoading } = useLead(id);
  const { data: matches, isLoading: matchesLoading } = useLeadMatches(id);
  const confirm = useConfirmLead(id);

  const [purpose, setPurpose] = useState("");
  const [budget, setBudget] = useState("");
  const [config, setConfig] = useState("");
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
    setBudget(c?.budget_value_lacs != null ? String(c.budget_value_lacs) : "");
    setConfig(c?.configuration || lead.configuration || "");
    setSocieties(c?.shortlisted_societies?.length ? c.shortlisted_societies : lead.society ? [lead.society] : []);
    setLocalities(c?.preferred_localities || []);
    setOffice(c?.office_willing || "");
    setOfficeDate(c?.office_preferred_date || "");
    setRemark(c?.remark || "");
  }, [lead]);

  if (isLoading) return <div className="card"><div className="empty" style={{ padding: 40 }}>Loading lead…</div></div>;
  if (!lead) return <div className="card"><div className="empty" style={{ padding: 40 }}>Lead not found.</div></div>;

  const budgetNum = parseFloat(budget);
  const invalid = { purpose: !purpose, budget: !(budgetNum > 0), config: !config, office: !office };
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
        budget_value_lacs: budgetNum,
        configuration: config,
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
            <div className="meta">
              {lead.phone} &nbsp;·&nbsp;{" "}
              <span className={`src ${srcClass(lead.source)}`} style={{ verticalAlign: "middle" }}>{srcLabel(lead.source)}</span>
              {lead.assigned_to && <> &nbsp;·&nbsp; {lead.assigned_to}</>}
              {lead.confirmed && <> &nbsp;·&nbsp; <span className="stage contacted">Qualified</span></>}
            </div>
          </div>
        </div>
      </div>

      <div className="detail-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {/* SOURCE-CAPTURED — editable */}
          <SourceCard lead={lead} />

          {/* CONVERSATION / REMARKS THREAD */}
          <NotesThread id={id} />


          {/* CONFIRMED Q1-Q6 */}
          <div className="card panel-pad">
            <div className="panel-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" />
              </svg>{" "}
              Lead data confirmed on call
            </div>

            <div className={field(invalid.purpose)}>
              <label>Q1. Purpose of buying property <span className="req">*</span></label>
              <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
                <option value="">Select…</option>
                {PURPOSES.map((p) => <option key={p}>{p}</option>)}
              </select>
            </div>

            <div className="two">
              <div className={field(invalid.budget)}>
                <label>Q2. Budget <span className="req">*</span></label>
                <div style={{ position: "relative" }}>
                  <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--muted)", fontWeight: 600 }}>₹</span>
                  <input type="number" min="0" placeholder="e.g. 85" value={budget} onChange={(e) => setBudget(e.target.value)} style={{ paddingLeft: 24 }} />
                </div>
                <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--emerald)", marginTop: 5 }}>
                  {budgetNum > 0 ? `= ₹${budgetNum} lacs` : "in lacs"}
                </div>
              </div>
              <div className={field(invalid.config)}>
                <label>Q3. Configuration <span className="req">*</span></label>
                <select value={config} onChange={(e) => setConfig(e.target.value)}>
                  <option value="">Select…</option>
                  {CONFIGS.map((c) => <option key={c}>{c}</option>)}
                </select>
              </div>
            </div>

            <div className="field">
              <label>Q4. Shortlisted societies <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— search master list</span></label>
              <AutocompleteChips
                value={societies}
                onChange={setSocieties}
                placeholder="Search societies…"
                fetcher={async (q) => (await api.searchSocieties(q)).items.map((h) => ({ label: h.society, sub: [h.locality, h.city].filter(Boolean).join(", ") }))}
              />
            </div>

            <div className="field">
              <label>Q5. Preferred localities <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— search master list</span></label>
              <AutocompleteChips
                value={localities}
                onChange={setLocalities}
                placeholder="Search localities…"
                fetcher={async (q) => (await api.searchLocalities(q)).items.map((l) => ({ label: l }))}
              />
            </div>

            <div className={field(invalid.office)}>
              <label>Q6. Willing to come to office? <span className="req">*</span></label>
              <select value={office} onChange={(e) => setOffice(e.target.value)}>
                <option value="">Select…</option>
                {OFFICE.map((o) => <option key={o}>{o}</option>)}
              </select>
            </div>

            {(office === "Yes" || office === "Maybe") && (
              <div className="field">
                <label>Preferred date</label>
                <input type="date" value={officeDate} onChange={(e) => setOfficeDate(e.target.value)} />
              </div>
            )}

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
            <div style={{ marginTop: 12 }}>
              <button className="btn green" onClick={save} disabled={confirm.isPending}>
                {confirm.isPending ? "Saving…" : lead.confirmed ? "Update confirmed data" : "Confirm & qualify lead"}
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT column — live matched inventory + supply */}
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <MatchPanel title="Best matches from inventory" tag="ACQUIRED PROPERTY" units={matches?.inventory ?? []} loading={matchesLoading} />
          <MatchPanel title="From supply pipeline" tag="SUPPLY CLOSURE TRACKER" units={matches?.supply ?? []} loading={matchesLoading} />
        </div>
      </div>
    </>
  );
}
