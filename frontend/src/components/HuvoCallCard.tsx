/* Huvo's calls to one lead, on the lead-detail page — newest first.

   A separate card from Call activity rather than merged into it, because the two
   record different things. Bonvoice logs the telephony leg an RM placed: did it
   connect, how long, here's the tape. Huvo logs what its bot got out of the
   conversation — an outcome, a score, what they said they wanted. Interleaving them
   would put "connected · 2:14" next to "qualified · wants 2BHK in Whitefield" and
   flatten the difference.

   Renders nothing when the bot has never called this lead: an empty card on a lead
   Huvo hasn't touched is just noise in the column. */
import { useState } from "react";
import { useLeadHuvoCalls, formatDateTime } from "../lib/queries";
import { HuvoCallDetail } from "../lib/api";
import RecordingPlayer, { RecordingLink } from "./RecordingPlayer";

/* Same three tiers as the Huvo Call Log's chips — a lead's card and the log must not
   colour the same outcome differently. */
const GOOD = new Set(["qualified", "site_visit_scheduled", "home_visit_scheduled",
                      "online_meeting_scheduled", "need_details_whatsapp"]);
const DEAD = new Set(["not_interested", "unqualified", "already_booked_elsewhere",
                      "another_location", "wrong_number", "duplicate_lead"]);

function outcomeStyle(outcome: string | null) {
  if (!outcome) return { background: "var(--panel-2)", color: "var(--muted)" };
  if (GOOD.has(outcome)) return { background: "var(--emerald-soft)", color: "#06694b" };
  if (DEAD.has(outcome)) return { background: "var(--coral-soft)", color: "var(--coral)" };
  return { background: "var(--amber-soft)", color: "var(--amber)" };
}

const pretty = (v: string) => v.replace(/_/g, " ");
const mmss = (s: number | null) =>
  s == null ? "—" : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/* The Huvo logo, same asset as the sidebar entry — this card is the one place on the
   lead page where the source of the information isn't obvious from context. */
const HuvoMark = () => (
  <img src="/huvo_icon.png" alt="" style={{ width: 16, height: 16, objectFit: "contain" }} />
);

function CallRow({ c }: { c: HuvoCallDetail }) {
  const [open, setOpen] = useState(false);
  const a = (c.payload?.analytics_data ?? {}) as Record<string, unknown>;

  /* Only what the caller actually volunteered. Huvo returns all 19 analytics keys on
     every call with most of them null, so rendering the full set would give a wall of
     dashes on a call where they said nothing. */
  const wants = ([
    ["Wants", a.type_of_property],
    ["Where", a.location],
    ["Project", a.project_name],
    ["Budget", a.budget_crores ? `${a.budget_crores} Cr` : null],
    ["Purpose", a.purpose],
    ["Why", a.interest_reason],
    ["Follow-up", a.follow_up_time],
    ["Site visit", a.site_visit_schedule],
  ] as [string, unknown][]).filter(([, v]) => v !== null && v !== undefined && v !== "");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span className="cfg-chip" style={outcomeStyle(c.call_outcome)}>
          {c.call_outcome ? pretty(c.call_outcome) : "no outcome"}
        </span>
        {c.is_interested === "yes" && (
          <span style={{ color: "var(--emerald)", fontSize: 12 }} title="Caller said they're interested">★</span>
        )}
        {c.lead_score != null && (
          <span style={{ fontSize: 11.5, color: "var(--muted)", fontFamily: "'Spline Sans Mono'" }}
                title="Huvo's lead score, 0–10">
            {c.lead_score}/10
          </span>
        )}
        <span style={{ fontSize: 12, color: "var(--ink-2)" }}>
          {formatDateTime(c.started_at) || formatDateTime(c.received_at) || "—"}
        </span>
        <span style={{ fontSize: 12, color: "var(--muted)", fontFamily: "'Spline Sans Mono'", marginLeft: "auto" }}>
          <RecordingLink url={c.recording_url}>{mmss(c.duration_sec)}</RecordingLink>
        </span>
      </div>

      {wants.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "3px 12px", fontSize: 12 }}>
          {wants.map(([label, value]) => (
            <span key={label}>
              <span style={{ color: "var(--muted)" }}>{label}: </span>
              <span style={{ color: "var(--ink-2)" }}>{String(value)}</span>
            </span>
          ))}
        </div>
      )}

      {c.summary && (
        <>
          {/* Clamped by default — these run to a full paragraph, and three of them
              unclamped would push everything below this card off the screen. */}
          <p style={{
            margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--muted)",
            ...(open ? {} : {
              display: "-webkit-box", WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical" as const, overflow: "hidden",
            }),
          }}>
            {c.summary}
          </p>
          <button className="btn ghost sm" style={{ alignSelf: "flex-start", fontSize: 11 }}
            onClick={() => setOpen((v) => !v)}>
            {open ? "Less" : "Read summary"}
          </button>
        </>
      )}

      {c.recording_url && <RecordingPlayer src={c.recording_url} />}
    </div>
  );
}

export default function HuvoCallCard({ leadId }: { leadId: string }) {
  const { data } = useLeadHuvoCalls(leadId);
  const calls = data?.items ?? [];
  if (calls.length === 0) return null;

  return (
    <div className="card" style={{ padding: 14 }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        borderBottom: "1px solid var(--line)", paddingBottom: 9, marginBottom: 11,
      }}>
        <HuvoMark />
        <b style={{ fontSize: 14 }}>Huvo calls</b>
        <span style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--muted)" }}>
          {calls.length} {calls.length === 1 ? "call" : "calls"}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 14, maxHeight: 460, overflowY: "auto" }}>
        {calls.map((c) => <CallRow key={c.id} c={c} />)}
      </div>
    </div>
  );
}
