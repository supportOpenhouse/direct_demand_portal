/* Live Calls — what the RM sees while the auto-dialer is working them.

   The dialer rings the RM's own handset first and bridges the lead second, so without
   this page they answer a call knowing nothing about who is on the other end. Three
   sections: who they're on with now, who's queued, and what they've already called
   today with whether the result is marked.

   Nothing here interrupts. A finished call drops into Today carrying a "needs result"
   badge and waits — gap_seconds defaults to 0, so the next lead can ring the instant
   the previous hangup lands, and a modal thrown up at that moment would be fighting a
   live call. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { LiveCallLead } from "../lib/api";
import { useCallResult, useMyCalls } from "../lib/queries";
import { useEventStream } from "../lib/useEventStream";
import { MissReasonModal } from "../components/CallConnected";
import { useToast } from "../components/Toast";

const istTime = (iso?: string | null) =>
  iso
    ? new Date(iso).toLocaleTimeString("en-IN", {
        timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit",
      })
    : "";

/** What we know about the lead, as a single line. Skips blanks so a sparse lead
    doesn't render " ·  · ". */
const details = (l: LiveCallLead) =>
  [l.society, l.city, l.configuration, l.budget].filter(Boolean).join(" · ");

function NowCalling({ lead }: { lead: LiveCallLead | null }) {
  const nav = useNavigate();
  if (!lead) {
    return (
      <div className="lc-card lc-idle">
        <div className="lc-eyebrow">No live call</div>
        <p className="lc-muted">
          The dialer will ring your handset when the next lead is ready.
        </p>
      </div>
    );
  }
  return (
    <div className="lc-card lc-live">
      <div className="lc-eyebrow lc-pulse">● Now calling</div>
      <h2 className="lc-name">{lead.name || "Unnamed lead"}</h2>
      {lead.phone && <div className="lc-phone">{lead.phone}</div>}
      <div className="lc-details">{details(lead)}</div>
      <div className="lc-meta">
        {lead.stage && <span className="chip">{lead.stage}</span>}
        <span className="lc-muted">
          {lead.ever_connected
            ? "spoken to before"
            : `never reached${lead.miss_count ? ` · ${lead.miss_count} misses` : ""}`}
        </span>
      </div>
      <button className="btn ghost" onClick={() => nav(`/leads/${lead.lead_id}`,
        { state: { from: "live-calls" } })}>
        Open lead ↗
      </button>
    </div>
  );
}

function Upcoming({ items, shared }: { items: LiveCallLead[]; shared: boolean }) {
  if (!items.length) return null;
  return (
    <section className="lc-section">
      <h3>Up next</h3>
      {/* Only the 'assigned' strategy stamps an owner up front. Under round_robin the
          queue is a shared pool and the next lead may well ring somebody else — the
          page says so rather than implying these are the RM's. */}
      {shared && (
        <p className="lc-muted lc-note">
          Shared pool — these may go to another RM.
        </p>
      )}
      <ol className="lc-queue">
        {items.map((l) => (
          <li key={l.id}>
            <span className="lc-qname">{l.name || "Unnamed lead"}</span>
            <span className="lc-muted">{details(l)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function CompletedRow({ lead }: { lead: LiveCallLead }) {
  const nav = useNavigate();
  const toast = useToast();
  const m = useCallResult();
  const [asking, setAsking] = useState(false);

  if (lead.call_result) {
    return (
      <li className="lc-done">
        <span className="lc-qname">{lead.name || "Unnamed lead"}</span>
        <span className="lc-muted">{istTime(lead.dialed_at)}</span>
        <span className={lead.call_result === "connected" ? "lc-ok" : "lc-miss"}>
          {lead.call_result === "connected" ? "✓ connected" : "✕ not reached"}
        </span>
      </li>
    );
  }

  // Yes goes straight to the lead in this same tab so the confirm form gets filled
  // while the call is fresh; LeadDetail shows a back link home from here.
  const yes = () =>
    m.mutate(
      { id: lead.lead_id, connected: true, queueItemId: lead.id },
      {
        onSuccess: () => nav(`/leads/${lead.lead_id}`, { state: { from: "live-calls" } }),
        onError: (e: any) => toast(e.message, "gold", "⚠"),
      },
    );

  return (
    <li className="lc-pending">
      <span className="lc-qname">{lead.name || "Unnamed lead"}</span>
      <span className="lc-muted">{istTime(lead.dialed_at)}</span>
      <span className="lc-badge">⚠ needs result</span>
      <span className="cc">
        <span className="cc-q">Connected?</span>
        <button className="cc-btn yes" disabled={m.isPending} onClick={yes}>Yes</button>
        <button className="cc-btn no" onClick={() => setAsking(true)}>No</button>
      </span>
      {asking && (
        <MissReasonModal
          leadId={lead.lead_id}
          queueItemId={lead.id}
          onClose={() => setAsking(false)}
        />
      )}
    </li>
  );
}

export default function LiveCalls() {
  // The stream only nudges; useMyCalls does the fetching, and polls instead whenever
  // the stream isn't healthy. One code path either way.
  const qc = useQueryClient();
  const healthy = useEventStream("/v1/dialer/my-calls/stream",
    () => qc.invalidateQueries({ queryKey: ["my-calls"] }));
  const { data, isLoading } = useMyCalls(healthy);

  if (isLoading) return <div className="page"><p className="lc-muted">Loading…</p></div>;

  const unmarked = (data?.completed || []).filter((c) => !c.call_result).length;

  return (
    <div className="page lc">
      <header className="lc-head">
        <div>
          <h1>Live Calls</h1>
          {data?.campaign ? (
            <p className="lc-muted">
              {data.campaign.name} · {data.campaign.window_start}–{data.campaign.window_end} IST
            </p>
          ) : (
            <p className="lc-muted">No campaign is dialling you right now.</p>
          )}
        </div>
        {/* Honest about which mechanism is running — a stalled page otherwise looks
            identical whether it's live or silently broken. */}
        <span className={healthy ? "lc-conn live" : "lc-conn poll"}>
          {healthy ? "live" : "polling"}
        </span>
      </header>

      <NowCalling lead={data?.now_calling ?? null} />

      <Upcoming items={data?.upcoming || []} shared={!!data?.upcoming_is_shared} />

      <section className="lc-section">
        <h3>
          Today · {data?.completed?.length || 0} calls
          {unmarked > 0 && <span className="lc-badge"> {unmarked} need a result</span>}
        </h3>
        {data?.completed?.length ? (
          <ul className="lc-list">
            {data.completed.map((c) => <CompletedRow key={c.id} lead={c} />)}
          </ul>
        ) : (
          <p className="lc-muted">Nothing dialled yet today.</p>
        )}
      </section>
    </div>
  );
}
