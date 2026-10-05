/* The Auto campaigns tab (spec §7, §9): repeat definitions. Each one names a seed campaign (whose list it
   repeats), a template and a schedule; the cron turns every due slot into an ordinary campaign run, which shows up
   on the Campaigns tab. A new one is saved INACTIVE — switching it on is a separate, deliberate click, since an
   active one messages real people on its own.

   `?seed=<campaignId>` (the campaign page's "Make it automatic") opens the form prefilled from that campaign.
   Read once; closing the form drops it from the URL so "+ New auto campaign" afterwards starts blank. */
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { SkeletonRows } from "../../components/Skeleton";
import { useToast } from "../../components/Toast";
import { WaAuto } from "../../lib/api";
import { useWaAutoAction, useWaAutos } from "../../lib/queries";
import AutoForm from "./AutoForm";

const REPEAT_LABEL = { everyone: "Everyone", non_responders: "Non-responders" } as const;
const fmtDay = (d: string) =>   // "2026-10-06" → "6 Oct" — a calendar date, so no timezone shift is wanted
  new Date(`${d}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const schedule = (a: WaAuto) => `${a.every_days === 1 ? "Every day" : `Every ${a.every_days} days`} · ${a.run_at}`;

export default function AutoTab() {
  const { data, isLoading, error } = useWaAutos();
  const act = useWaAutoAction();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [initialSeed] = useState(params.get("seed"));
  const [editing, setEditing] = useState<WaAuto | "new" | null>(initialSeed ? "new" : null);
  const [seed, setSeed] = useState<string | null>(initialSeed);
  const items = data?.items ?? [];

  const closeForm = () => {
    setEditing(null);
    setSeed(null);
    if (params.has("seed")) setParams((p) => { p.delete("seed"); return p; }, { replace: true });
  };
  // run-now is the one action that sends on the spot, so it asks first
  const run = (a: WaAuto, action: "activate" | "deactivate" | "run-now") => {
    if (action === "run-now" && !window.confirm(`Run "${a.name}" now? It queues today's run and starts sending inside its send window.`)) return;
    act.mutate({ id: a.id, action }, {
      onSuccess: () => toast(action === "activate" ? "Switched on" : action === "deactivate" ? "Switched off" : "Run queued", "green"),
      onError: (e: any) => toast(e.message, "gold"),   // 503 names the missing template-app settings
    });
  };

  return (
    <>
      <div className="wc-bar"><button className="btn primary sm" onClick={() => setEditing("new")}>+ New auto campaign</button></div>
      <div className="card table-wrap">
        {isLoading ? <SkeletonRows rows={3} /> : error ? (
          <div className="empty" style={{ padding: 40 }}>Couldn't load the auto campaigns — {error.message}</div>
        ) : !items.length ? (
          <div className="empty" style={{ padding: 40 }}>
            No auto campaigns yet — press + New auto campaign, or open a campaign and choose Make it automatic.
          </div>
        ) : (
          <table className="wc-table">
            <thead>
              <tr><th>Name</th><th>Template</th><th>Schedule</th><th>Repeat</th><th>Next run</th><th>Last run</th><th>Active</th><th /></tr>
            </thead>
            <tbody>{items.map((a) => (
              <tr key={a.id}>
                <td>{a.name}{a.status_note && <div className="wc-hint">{a.status_note}</div>}</td>
                <td className="cell-text"><span title={a.template_name}>{a.template_name}</span></td>
                <td className="cell-tight">{schedule(a)}</td>
                <td className="cell-tight">{REPEAT_LABEL[a.repeat_mode] ?? a.repeat_mode}</td>
                <td className="cell-tight">{a.active ? `${fmtDay(a.next_slot)} · ${a.run_at}` : "—"}</td>
                <td className="cell-tight">{a.last_run ? (
                  <>
                    <Link to={`/wa-campaigns/${a.last_run.id}`} className="wc-link">{a.last_run.name}</Link>
                    <div className="wc-sub">sent {a.last_run.counts.sent.toLocaleString("en-IN")} · replied {a.last_run.counts.replied.toLocaleString("en-IN")}</div>
                  </>
                ) : "—"}</td>
                <td className="cell-tight">
                  <button role="switch" aria-checked={a.active} aria-label={`${a.active ? "Switch off" : "Switch on"} ${a.name}`}
                    className={"switch" + (a.active ? " on" : "")} disabled={act.isPending}
                    onClick={() => run(a, a.active ? "deactivate" : "activate")} />
                </td>
                <td className="cell-tight">
                  <button className="btn ghost sm" onClick={() => setEditing(a)}>Edit</button>
                  {a.active && <button className="btn ghost sm" style={{ marginLeft: 6 }} disabled={act.isPending}
                    onClick={() => run(a, "run-now")}>Run now</button>}
                </td>
              </tr>))}</tbody>
          </table>
        )}
      </div>
      {editing && <AutoForm a={editing === "new" ? undefined : editing} seedId={editing === "new" ? seed : null} onClose={closeForm} />}
    </>
  );
}
