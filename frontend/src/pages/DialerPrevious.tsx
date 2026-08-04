/* Previous Campaigns — pick a past campaign, see what it was set to, how it did,
   and every call it placed.

   The call table is the Call Log page's own endpoint with a campaign_id filter, so
   the rows can't drift from what Bonvoice Call Log shows. Attribution comes from
   call_logs.campaign_id, stamped when the callback lands — see routers/bonvoice.py. */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useCallLog, useCampaign, useCampaigns, callDuration, formatDateTime } from "../lib/queries";
import RecordingPlayer from "../components/RecordingPlayer";
import { CampaignRow } from "../lib/api";

const PAGE = 50;

const STATUS_TONE: Record<string, string> = {
  running: "var(--emerald)", paused: "var(--amber)",
  done: "var(--slate)", draft: "var(--slate)",
};

const STRATEGY_LABEL: Record<string, string> = {
  assigned: "Assigned leads", round_robin: "Round-robin", least_load: "Least load",
};

function Tile({ n, label, hint }: { n: number | string; label: string; hint?: string }) {
  return (
    <div className="dl-stat" title={hint}>
      <b>{n}</b><span>{label}</span>
    </div>
  );
}

export default function DialerPrevious() {
  const campaigns = useCampaigns();
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
            <span className="dl-count">
              {c?.started_at ? formatDateTime(c.started_at) : "never started"}
            </span>
          </div>

          <div className="dl-stats" style={{ marginBottom: 12 }}>
            <Tile n={stats?.unique_leads ?? 0} label="Unique leads called"
                  hint="Leads dialled at least once — a lead rung three times counts once here" />
            <Tile n={stats?.total_calls ?? 0} label="Total calls placed"
                  hint="Every attempt, retries included" />
            <Tile n={stats?.connected ?? 0} label="Connected" />
            <Tile n={stats?.total ?? 0} label="Queued" hint="Leads the rules put in this campaign's queue" />
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

        <section className="card">
          <div className="dl-cardhead">
            <div><div className="dl-eyebrow">Settings</div><h2 className="dl-cardtitle">How it was set up</h2></div>
          </div>
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
                      {r.lead_id ? <Link to={`/leads/${r.lead_id}`}>{r.lead_name || "View lead"}</Link>
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
