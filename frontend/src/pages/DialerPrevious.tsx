/* Previous Campaigns — pick a past campaign, see what it was set to, how it did,
   and every call it placed.

   The call table is the Call Log page's own endpoint with a campaign_id filter, so
   the rows can't drift from what Bonvoice Call Log shows. Attribution comes from
   call_logs.campaign_id, stamped when the callback lands — see routers/bonvoice.py. */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  useCallLog, useCampaign, useCampaignAction, useCampaigns, useDialerFields,
  callDuration, formatDateTime,
} from "../lib/queries";
import RecordingPlayer from "../components/RecordingPlayer";
import { useToast } from "../components/Toast";
import { CampaignFeedRow, CampaignRow, DialerField, RuleNode } from "../lib/api";

const PAGE = 50;

/* ── live feed row (moved here with the live panel) ─────────────────────── */
const outcomeColor = (r: CampaignFeedRow) =>
  r.status === "dialing" ? "var(--amber)"
    : r.status === "failed" ? "var(--coral)"
    : r.answered ? "var(--emerald)" : "var(--muted)";

/* A row only leaves "dialing" when Bonvoice posts the hangup callback. If that never
   arrives the call looks stuck ringing until the server reaps it minutes later — so
   say what's actually happening instead of showing a stale state. */
const RINGING_GRACE_MS = 90_000;

const outcomeText = (r: CampaignFeedRow) => {
  if (r.status === "failed") return r.detail || "Not placed";
  if (r.status !== "dialing") return r.answered ? "Connected" : (r.outcome || "No answer");
  const ringingFor = r.dialed_at ? Date.now() - new Date(r.dialed_at).getTime() : 0;
  return ringingFor > RINGING_GRACE_MS ? "Ringing… (no hangup callback yet)" : "Ringing…";
};

const hhmm = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }) : "";

const STATUS_TONE: Record<string, string> = {
  running: "var(--emerald)", paused: "var(--amber)",
  done: "var(--slate)", draft: "var(--slate)",
};

const STRATEGY_LABEL: Record<string, string> = {
  assigned: "Assigned leads", round_robin: "Round-robin", least_load: "Least load",
};

/* How each operator reads in prose. The builder shows a <select>; here the rule is
   history, so it should read as a sentence rather than a form control. */
const OP_PHRASE: Record<string, string> = {
  "IN": "is any of", "NOT IN": "is none of", "BETWEEN": "between", "IS": "is",
};

/* A field with no value set compiles to TRUE (see compile_rules) — i.e. it filters
   nothing. Saying "any" is the honest rendering; an empty chip list looks broken. */
function condText(node: Extract<RuleNode, { type: "condition" }>, f?: DialerField) {
  const label = f?.label || node.field.replace(/_/g, " ").replace(/^./, (s) => s.toUpperCase());
  const v = node.value;
  if (Array.isArray(v)) {
    if (node.op === "BETWEEN") {
      const [a, b] = v as string[];
      return { label, phrase: a || b ? `between ${a || "…"} and ${b || "…"}` : "any date", chips: [] };
    }
    return v.length
      ? { label, phrase: OP_PHRASE[node.op] || node.op, chips: v as string[] }
      : { label, phrase: "any value", chips: [] };
  }
  if (typeof v === "boolean") return { label, phrase: `is ${v ? "yes" : "no"}`, chips: [] };
  return { label, phrase: `${node.op} ${v}`, chips: [] };
}

function RuleView({ node, fields }: { node: RuleNode; fields: DialerField[] }) {
  if (node.type === "condition") {
    const { label, phrase, chips } = condText(node, fields.find((f) => f.key === node.field));
    return (
      <div className="rv-cond">
        <b>{label}</b> <span className="rv-op">{phrase}</span>
        {chips.map((c) => <span key={c} className="rv-chip">{c}</span>)}
      </div>
    );
  }
  if (!node.children.length) {
    return <div className="rv-cond"><span className="rv-op">No conditions — matched every lead.</span></div>;
  }
  return (
    <div className="rv-group">
      <div className="rv-comb">Match {node.combinator === "AND" ? "all" : "any"} of</div>
      <div className="rv-kids">
        {node.children.map((c) => <RuleView key={c.id} node={c} fields={fields} />)}
      </div>
    </div>
  );
}

function Tile({ n, label, hint }: { n: number | string; label: string; hint?: string }) {
  return (
    <div className="dl-stat" title={hint}>
      <b>{n}</b><span>{label}</span>
    </div>
  );
}

export default function DialerPrevious() {
  const toast = useToast();
  const campaigns = useCampaigns();
  const action = useCampaignAction();
  // Field labels for the rule tree ("stage" → "Lead stage") and RM display names for
  // the live panel. Cached under the same key the scheduler uses — one request total.
  const dialerMeta = useDialerFields();
  const fields = dialerMeta.data?.fields ?? [];
  const [activeId, setActiveId] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const items = campaigns.data?.items ?? [];

  // Land on the newest campaign so the page is never an empty shell. Only fires
  // while nothing is picked, so it can't yank you off a campaign you selected.
  useEffect(() => {
    if (!activeId && items.length) setActiveId(items[0].id);
  }, [activeId, items]);

  const detail = useCampaign(activeId);
  const c = detail.data?.campaign;
  const stats = detail.data?.stats;

  const calls = useCallLog(
    { campaign_id: activeId || undefined, limit: PAGE, offset: page * PAGE },
    !!activeId,  // never fire unscoped — that would fetch every call in the system
  );
  const rows = activeId ? calls.data?.items ?? [] : [];
  const total = activeId ? calls.data?.total ?? 0 : 0;
  const start = total === 0 ? 0 : page * PAGE + 1;
  const end = Math.min(total, (page + 1) * PAGE);

  const pick = (id: string) => { setActiveId(id); setPage(0); };

  // A campaign is "live" until it's stopped: paused still holds a queue and can be
  // resumed, so its panel and controls stay up.
  const isLive = c?.status === "running" || c?.status === "paused";
  const running = c?.status === "running";
  const perRM = detail.data?.per_rm || {};
  const feed = detail.data?.feed || [];
  const rmName = Object.fromEntries((dialerMeta.data?.rms || []).map((r) => [r.email, r.name]));

  const act = (a: "start" | "pause" | "stop") =>
    activeId && action.mutate({ id: activeId, action: a }, {
      // The server refuses a resume that would double-book an RM (409) — surface
      // that reason rather than leaving the button looking broken.
      onError: (e: any) => toast(e.message, "gold", "⚠"),
    });

  if (campaigns.isLoading) return <div className="card dl-empty" style={{ padding: 28 }}>Loading campaigns…</div>;
  if (campaigns.isError) {
    return <div className="card dl-empty" style={{ padding: 28 }}>
      {(campaigns.error as Error).message === "admin only"
        ? "The auto dialer is admin-only — it rings other people's phones."
        : (campaigns.error as Error).message}
    </div>;
  }
  if (!items.length) {
    return <div className="card dl-empty" style={{ padding: 28 }}>
      No campaigns yet. <Link to="/dialer/schedule">Schedule one</Link>.
    </div>;
  }

  return (
    <div className="dl-layout" style={{ gridTemplateColumns: "260px 1fr" }}>
      <aside className="dl-side">
        {/* Only while a campaign is actually live — a finished one has its totals in
            the Summary card, and a permanent row of zeros is just furniture. */}
        {isLive && (
          <>
            <div className="card dl-livecard">
              <div className="dl-livehead">
                <span className={"dl-livedot" + (running ? " on" : "")} />
                {running ? "Dialing live" : "Campaign paused"}
              </div>
              <div className="dl-stats">
                <div className="dl-stat"><b>{stats?.pending ?? 0}</b><span>In queue</span></div>
                <div className="dl-stat"><b>{stats?.live ?? 0}</b><span>On call</span></div>
                <div className="dl-stat"><b>{(stats?.done ?? 0) + (stats?.failed ?? 0)}</b><span>Done</span></div>
              </div>
            </div>

            <div className="card">
              <div className="dl-eyebrow">Relationship managers</div>
              <div className="dl-rmlist">
                {(c?.rms || []).map((email) => {
                  const s = perRM[email];
                  const onCall = !!s?.live;
                  return (
                    <div key={email} className="dl-rmrow">
                      <span className={"dl-statdot" + (onCall ? " pulse" : "")}
                        style={{ background: onCall ? "var(--amber)" : "var(--emerald)" }} />
                      <div className="dl-rmmeta">
                        <b>{rmName[email] || email}</b>
                        <span>{onCall ? "On a call" : running ? "Waiting for the next lead" : "Idle"}</span>
                      </div>
                      <span className="dl-donebadge">{s?.done ?? 0}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="card">
              <div className="dl-eyebrow">Recent calls</div>
              <div className="dl-feed">
                {!feed.length && <div className="dl-empty">No calls yet.</div>}
                {feed.map((r) => (
                  <div key={r.lead_id + (r.dialed_at || "")} className="dl-feedrow">
                    <span className="dl-feeddot" style={{ background: outcomeColor(r) }} />
                    <div className="dl-rmmeta">
                      <b>{r.lead_name || r.society || "Lead"}</b>
                      <span>{rmName[r.rm_email || ""] || r.rm_email} · {outcomeText(r)}</span>
                    </div>
                    <span className="dl-feedtime">{hhmm(r.ended_at || r.dialed_at)}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        <div className="card">
          <div className="dl-eyebrow">Campaigns</div>
          <div className="dl-rmlist">
            {items.map((r: CampaignRow) => (
              <button key={r.id} className={"dl-camprow" + (r.id === activeId ? " on" : "")}
                onClick={() => pick(r.id)}>
                <span className="dl-statdot" style={{ background: STATUS_TONE[r.status] || "var(--slate)" }} />
                <div className="dl-rmmeta">
                  <b>{r.name}</b>
                  <span>
                    {r.status} · {r.unique_leads} lead{r.unique_leads === 1 ? "" : "s"}
                    {r.total_calls > r.unique_leads && ` · ${r.total_calls} calls`}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </aside>

      <main className="dl-main">
        <section className="card">
          <div className="dl-cardhead">
            <div>
              <div className="dl-eyebrow">Summary</div>
              <h2 className="dl-cardtitle">{c?.name || "—"}</h2>
            </div>
            {isLive ? (
              <span style={{ display: "flex", gap: 6 }}>
                <button className="btn sm" onClick={() => act(running ? "pause" : "start")}>
                  {running ? "Pause" : "Resume"}
                </button>
                <button className="btn sm" onClick={() => act("stop")}>Stop</button>
              </span>
            ) : (
              <span className="dl-count">
                {c?.started_at ? formatDateTime(c.started_at) : "never started"}
              </span>
            )}
          </div>

          <div className="dl-stats" style={{ marginBottom: 12 }}>
            <Tile n={stats?.unique_leads ?? 0} label="Unique leads called"
                  hint="Leads dialled at least once — a lead rung three times counts once here" />
            <Tile n={stats?.total_calls ?? 0} label="Total calls placed"
                  hint="Every attempt, retries included" />
            <Tile n={stats?.connected ?? 0} label="Connected" />
          </div>

          {/* Only worth saying when retries actually happened — on a single-attempt
              campaign the two numbers are identical and the note is noise. */}
          {!!stats && stats.total_calls > stats.unique_leads && (
            <p className="dl-note">
              <b>{stats.total_calls - stats.unique_leads}</b> of these were repeat attempts —
              this campaign allowed up to {c?.max_attempts} per lead, {c?.cooldown_minutes} minutes apart.
            </p>
          )}
        </section>

        {/* All three builder steps in one card — as a record of what was asked for,
            they read as one instruction, not three separate settings screens. */}
        <section className="card">
          <div className="dl-cardhead">
            <div>
              <div className="dl-eyebrow">Setup</div>
              <h2 className="dl-cardtitle">Campaign instructions</h2>
            </div>
            {/* `targeted`, not `total`: under the 'assigned' strategy the queue holds
                every rule match and then skips the ones nobody in the pool owns, so
                `total` reported 1727 for a campaign aimed at one RM's 4 leads. */}
            <span className="dl-count"><b>{stats?.targeted ?? 0}</b> targeted leads</span>
          </div>

          <div className="dl-substep">Who to call</div>
          {c ? <RuleView node={c.rules} fields={fields} />
             : <div className="dl-empty">—</div>}
          <p className="dl-note">
            Leads with no phone number, and test rows, were never dialled whatever the rules say.
          </p>

          <div className="dl-substep divider">Who calls them, and how fast</div>
          <div className="dl-settings">
            <label className="dl-field"><span>Who called</span>
              <input className="dl-input" disabled
                value={STRATEGY_LABEL[c?.strategy || ""] || c?.strategy || "—"} />
              <em className="dl-hint">{(c?.rms || []).join(", ") || "no RMs"}</em>
            </label>
            <label className="dl-field"><span>Calling window (IST)</span>
              <input className="dl-input" disabled value={`${c?.window_start ?? "—"} – ${c?.window_end ?? "—"}`} />
            </label>
            <label className="dl-field"><span>Gap between calls</span>
              <input className="dl-input" disabled value={c ? `${c.gap_seconds}s` : "—"} />
            </label>
            <label className="dl-field"><span>Attempts / cooldown</span>
              <input className="dl-input" disabled
                value={c ? `${c.max_attempts} · ${c.cooldown_minutes} min` : "—"} />
            </label>
          </div>
        </section>

        <section className="card panel-pad">
          <div className="section-head" style={{ marginBottom: 10 }}>
            <h3 className="sec-title">Calls placed</h3>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>
              {calls.isFetching ? "loading…" : `${total} leg${total === 1 ? "" : "s"}`}
            </span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 150 }}>When</th>
                  <th style={{ minWidth: 120 }}>Lead</th>
                  <th>From → To</th>
                  <th style={{ minWidth: 150 }}>Status</th>
                  <th style={{ width: 70 }}>Duration</th>
                  <th style={{ width: 110 }}>Recording</th>
                  <th>Placed by</th>
                </tr>
              </thead>
              <tbody>
                {calls.isLoading ? (
                  <tr><td colSpan={7}><div className="empty" style={{ padding: 24 }}>Loading calls…</div></td></tr>
                ) : rows.length === 0 ? (
                  <tr><td colSpan={7}><div className="empty" style={{ padding: 24 }}>
                    No calls attributed to this campaign.
                    {/* Campaigns that ran before call_logs.campaign_id existed only kept
                        the last attempt per lead — earlier retries can't be recovered. */}
                    {!!stats?.total_calls && " Calls placed before campaign tracking was added aren't attributed."}
                  </div></td></tr>
                ) : rows.map((r) => (
                  <tr key={`${r.call_id}-${r.leg}`}>
                    <td style={{ fontSize: 12, whiteSpace: "nowrap", fontFamily: "'Spline Sans Mono'" }}>
                      {formatDateTime(r.start_at) || "—"}
                    </td>
                    <td style={{ fontSize: 12.5 }}>
                      {r.lead_id
                        ? <Link className="lead-link" to={`/leads/${r.lead_id}`}>{r.lead_name || "View lead"}</Link>
                        : <span style={{ color: "var(--muted)" }}>—</span>}
                    </td>
                    <td style={{ fontSize: 12, fontFamily: "'Spline Sans Mono'", whiteSpace: "nowrap" }}>
                      {r.source_number || "—"} → {r.destination_number || "—"}
                    </td>
                    <td style={{ fontSize: 12.5 }}>
                      <span className="cfg-chip" style={{
                        background: r.answered ? "var(--emerald-soft)" : "var(--slate-soft)",
                        color: r.answered ? "#06694b" : "var(--slate)",
                      }}>
                        {r.answered ? "connected" : "not connected"}
                      </span>{" "}
                      <span style={{ color: "var(--muted)", fontSize: 11.5 }}>{r.status || r.agent_status || ""}</span>
                    </td>
                    <td style={{ fontSize: 12, fontFamily: "'Spline Sans Mono'" }}>
                      {callDuration(r.start_at, r.end_at)}
                    </td>
                    <td>
                      {r.recording_url ? <RecordingPlayer src={r.recording_url} />
                                       : <span style={{ color: "var(--muted)" }}>—</span>}
                    </td>
                    <td style={{ fontSize: 12, color: "var(--muted)" }}>{r.placed_by || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>
              {total > 0 ? `${start}–${end} of ${total.toLocaleString("en-IN")}` : "—"}
            </span>
            <span style={{ display: "flex", gap: 6 }}>
              <button className="btn sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
              <button className="btn sm" disabled={end >= total} onClick={() => setPage((p) => p + 1)}>Next</button>
            </span>
          </div>
        </section>
      </main>
    </div>
  );
}
