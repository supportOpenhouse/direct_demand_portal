/* Calls placed to one lead, on the lead-detail page — newest first, with the
   recording where Bonvoice kept one.

   Renders nothing until a call has actually been made: an empty card on a lead
   nobody has rung yet is just noise in the column. */
import { useLeadCalls, callDuration, formatDateTime } from "../lib/queries";
import { LeadCallRow } from "../lib/api";

const IconPhone = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91" />
  </svg>
);

export default function CallActivityCard({ leadId }: { leadId: string }) {
  const { data } = useLeadCalls(leadId);
  const calls = data?.items ?? [];
  if (calls.length === 0) return null;

  return (
    <div className="card" style={{ padding: 14 }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        borderBottom: "1px solid var(--line)", paddingBottom: 9, marginBottom: 11,
      }}>
        <span style={{ width: 16, height: 16, color: "var(--emerald)", display: "inline-flex" }}>
          <IconPhone />
        </span>
        <b style={{ fontSize: 14 }}>Call activity</b>
        <span style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--muted)" }}>
          {calls.length} {calls.length === 1 ? "call" : "calls"}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10, maxHeight: 420, overflowY: "auto" }}>
        {calls.map((c: LeadCallRow) => (
          <div key={`${c.call_id}-${c.leg}`} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span className="cfg-chip" style={{
                background: c.answered ? "var(--emerald-soft)" : "var(--slate-soft)",
                color: c.answered ? "#06694b" : "var(--slate)",
              }}>
                {c.answered ? "connected" : "not connected"}
              </span>
              <span style={{ fontSize: 12, color: "var(--ink-2)" }}>{formatDateTime(c.start_at) || "—"}</span>
              <span style={{ fontSize: 12, color: "var(--muted)", fontFamily: "'Spline Sans Mono'", marginLeft: "auto" }}>
                {callDuration(c.start_at, c.end_at)}
              </span>
            </div>
            {/* ponytail: native player, straight off Bonvoice's url — same as the
                Call Log page. Zero-duration calls have no file, so no player. */}
            {c.recording_url && (
              <audio controls preload="none" src={c.recording_url} style={{ height: 32, width: "100%" }} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
