/* Auto Dialer — build a queue from a rule tree, hand it to a pool of RMs, watch it run.

   Nothing dials from this page. The rule tree, the RM pool and the pacing are saved as
   a campaign; a loop on the server places the calls and the Bonvoice hangup callback is
   what frees an RM for the next lead. Closing the tab doesn't stop anything — Pause does.

   Concurrency is the size of the pool: Click2Call rings the RM's own handset first, so
   one RM can only ever hold one live call. Three RMs = three calls at a time. */
import { useEffect, useMemo, useState } from "react";
import {
  useCampaign, useCampaignAction, useCampaigns, useCreateCampaign, useDialerFields,
  useRulePreview,
} from "../lib/queries";
import { CampaignFeedRow, DialerField, RuleGroup, RuleNode, RuleValue } from "../lib/api";
import { useDebounce } from "../lib/useDebounce";
import { useToast } from "../components/Toast";

const nid = () => "n" + Math.random().toString(36).slice(2, 8);

const STRATEGIES: { key: string; label: string; hint: string }[] = [
  { key: "assigned", label: "Assigned Leads", hint: "Each lead is called by the RM it's already assigned to" },
  { key: "round_robin", label: "Round-robin", hint: "Longest-idle RM takes the next lead" },
  { key: "least_load", label: "Least load", hint: "Whoever has made the fewest calls so far" },
];

const emptyTree = (): RuleGroup => ({
  id: nid(), type: "group", combinator: "AND",
  children: [{ id: nid(), type: "condition", field: "stage", op: "IN", value: [] }],
});

const defaultValue = (f: DialerField): RuleValue =>
  f.kind === "daterange" ? ["", ""] : f.kind === "number" ? 0 : f.kind === "bool" ? false : [];

/* ── tree edits (immutable, so React sees every change) ─────────────────── */
function mapTree(node: RuleNode, fn: (n: RuleNode) => RuleNode): RuleNode {
  const m = fn(node);
  return m.type === "group" ? { ...m, children: m.children.map((c) => mapTree(c, fn)) } : m;
}
function removeById(node: RuleNode, id: string): RuleNode {
  if (node.type !== "group") return node;
  return { ...node, children: node.children.filter((c) => c.id !== id).map((c) => removeById(c, id)) };
}

/* ── condition row ──────────────────────────────────────────────────────── */
function Condition({ node, fields, update, remove }: {
  node: Extract<RuleNode, { type: "condition" }>;
  fields: DialerField[];
  update: (id: string, patch: Partial<RuleNode>) => void;
  remove: (id: string) => void;
}) {
  const f = fields.find((x) => x.key === node.field) || fields[0];
  if (!f) return null;
  const val = node.value;

  return (
    <div className="dl-cond">
      <select className="dl-select" value={node.field}
        onChange={(e) => {
          const next = fields.find((x) => x.key === e.target.value)!;
          update(node.id, { field: next.key, op: next.ops[0], value: defaultValue(next) } as any);
        }}>
        {fields.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
      </select>

      {f.ops.length > 1 ? (
        <select className="dl-select dl-op" value={node.op}
          onChange={(e) => update(node.id, { op: e.target.value } as any)}>
          {f.ops.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : <span className="dl-op-static">is between</span>}

      <div className="dl-val">
        {f.kind === "multi" && (
          <div className="dl-pillrow">
            {f.options.length === 0 && <span className="dl-empty">no values in the data yet</span>}
            {f.options.map((o) => {
              const on = Array.isArray(val) && (val as string[]).includes(o);
              return (
                <button key={o} className={"dl-pill" + (on ? " on" : "")}
                  onClick={() => {
                    const cur = (val as string[]) || [];
                    update(node.id, { value: on ? cur.filter((x) => x !== o) : [...cur, o] } as any);
                  }}>{o}</button>
              );
            })}
          </div>
        )}
        {f.kind === "number" && (
          <input type="number" className="dl-input" style={{ width: 90 }} value={String(val)}
            onChange={(e) => update(node.id, { value: Number(e.target.value) } as any)} />
        )}
        {f.kind === "daterange" && (
          <div className="dl-daterow">
            <input type="date" className="dl-input" value={(val as string[])[0] || ""}
              onChange={(e) => update(node.id, { value: [e.target.value, (val as string[])[1] || ""] } as any)} />
            <span className="dl-dash">–</span>
            <input type="date" className="dl-input" value={(val as string[])[1] || ""}
              onChange={(e) => update(node.id, { value: [(val as string[])[0] || "", e.target.value] } as any)} />
          </div>
        )}
        {f.kind === "bool" && (
          <div className="dl-pillrow">
            {[true, false].map((b) => (
              <button key={String(b)} className={"dl-pill" + (Boolean(val) === b ? " on" : "")}
                onClick={() => update(node.id, { value: b } as any)}>{b ? "Yes" : "No"}</button>
            ))}
          </div>
        )}
      </div>
      <button className="dl-x" title="Remove" onClick={() => remove(node.id)}>×</button>
    </div>
  );
}

function Group({ node, fields, depth, update, remove, addChild }: {
  node: RuleGroup;
  fields: DialerField[];
  depth: number;
  update: (id: string, patch: Partial<RuleNode>) => void;
  remove: (id: string) => void;
  addChild: (pid: string, child: RuleNode) => void;
}) {
  const firstField = fields[0];
  return (
    <div className={"dl-group" + (depth > 0 ? " nested" : "")}>
      <div className="dl-grouphead">
        <div className="dl-seg">
          {(["AND", "OR"] as const).map((c) => (
            <button key={c} className={"dl-segbtn" + (node.combinator === c ? " on" : "")}
              onClick={() => update(node.id, { combinator: c } as any)}>{c}</button>
          ))}
        </div>
        <span className="dl-matchtxt">{node.combinator === "AND" ? "match all of" : "match any of"}</span>
        <div className="dl-spacer" />
        <button className="dl-addbtn" onClick={() => addChild(node.id, {
          id: nid(), type: "condition", field: firstField.key, op: firstField.ops[0],
          value: defaultValue(firstField),
        })}>+ Condition</button>
        {depth < 2 && (
          <button className="dl-addbtn ghost" onClick={() =>
            addChild(node.id, { id: nid(), type: "group", combinator: "OR", children: [] })}>
            + Group
          </button>
        )}
        {depth > 0 && <button className="dl-x" onClick={() => remove(node.id)}>×</button>}
      </div>
      <div className="dl-children">
        {node.children.length === 0 && <div className="dl-empty">No conditions — this group matches everyone.</div>}
        {node.children.map((c) => c.type === "group"
          ? <Group key={c.id} node={c} fields={fields} depth={depth + 1} update={update} remove={remove} addChild={addChild} />
          : <Condition key={c.id} node={c} fields={fields} update={update} remove={remove} />)}
      </div>
    </div>
  );
}

/* ── live feed row ──────────────────────────────────────────────────────── */
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

/* What a brand-new campaign starts as. Kept in one place because the form has to
   be able to snap back to it when you leave a saved campaign — see resetForm. */
const DEFAULTS = {
  name: "",  // deliberately blank — naming the campaign is required, not defaulted
  strategy: "assigned",
  gap: 0,
  win: { start: "10:00", end: "19:00" },
  attempts: 1,
  cooldown: 360,
};

/* ── page ───────────────────────────────────────────────────────────────── */
export default function Dialer() {
  const toast = useToast();
  const meta = useDialerFields();
  const campaigns = useCampaigns();
  const createCampaign = useCreateCampaign();
  const action = useCampaignAction();

  const [name, setName] = useState(DEFAULTS.name);
  const [tree, setTree] = useState<RuleGroup>(emptyTree);
  const [rms, setRms] = useState<string[]>([]);
  const [strategy, setStrategy] = useState(DEFAULTS.strategy);
  const [gap, setGap] = useState(DEFAULTS.gap);
  const [win, setWin] = useState(DEFAULTS.win);
  const [attempts, setAttempts] = useState(DEFAULTS.attempts);
  const [cooldown, setCooldown] = useState(DEFAULTS.cooldown);
  const [activeId, setActiveId] = useState<string | null>(null);

  const fields = meta.data?.fields || [];
  const pool = meta.data?.rms || [];
  const debouncedTree = useDebounce(tree, 350);
  const preview = useRulePreview(debouncedTree, strategy, rms);
  const detail = useCampaign(activeId);

  const update = (id: string, patch: Partial<RuleNode>) =>
    setTree((t) => mapTree(t, (n) => (n.id === id ? { ...n, ...patch } as RuleNode : n)) as RuleGroup);
  const remove = (id: string) => setTree((t) => removeById(t, id) as RuleGroup);
  const addChild = (pid: string, child: RuleNode) =>
    setTree((t) => mapTree(t, (n) =>
      n.id === pid && n.type === "group" ? { ...n, children: [...n.children, child] } : n) as RuleGroup);

  const matched = preview.data?.count ?? 0;
  // 'assigned' + a chosen pool: the count is what those RMs own, not every match
  const scoped = !!preview.data?.scoped;
  const live = detail.data;
  const running = live?.campaign.status === "running";
  const perRM = live?.per_rm || {};
  const stats = live?.stats;

  const rmName = useMemo(
    () => Object.fromEntries(pool.map((r) => [r.email, r.name])),
    [pool],
  );

  /* Opening a saved campaign showed the new-campaign defaults: every Step 1–3
     input is local state that nothing ever populated from the row. Steps 1–3 are
     all disabled while activeId is set, so this only ever writes to a read-only
     form — it can't fight typing.

     Keyed on the campaign *id*, not on `live`: useCampaign polls every 2s for the
     live stats, and depending on the object would re-set all eight fields twice a
     second for no reason. */
  const loadedId = live?.campaign.id;
  useEffect(() => {
    const c = live?.campaign;
    if (!c) return;
    setName(c.name);
    setTree(c.rules as RuleGroup);
    setRms(c.rms);
    setStrategy(c.strategy);
    setGap(c.gap_seconds);
    setWin({ start: c.window_start, end: c.window_end });
    setAttempts(c.max_attempts);
    setCooldown(c.cooldown_minutes);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadedId]);

  function resetForm() {
    setActiveId(null);
    setName(DEFAULTS.name);
    setTree(emptyTree());
    setRms([]);
    setStrategy(DEFAULTS.strategy);
    setGap(DEFAULTS.gap);
    setWin(DEFAULTS.win);
    setAttempts(DEFAULTS.attempts);
    setCooldown(DEFAULTS.cooldown);
  }

  function launch() {
    // Named first: "Untitled campaign" ×6 in Previous Campaigns is unreadable, and
    // the name is the only thing distinguishing two runs of the same rules.
    if (!name.trim()) return toast("Give this campaign a name", "gold", "⚠");
    if (!rms.length) return toast("Pick at least one RM — they do the calling", "gold", "⚠");
    if (!matched) return toast("No leads match these rules", "gold", "⚠");
    createCampaign.mutate({
      name: name.trim(), rules: tree, rms, strategy,
      gap_seconds: gap, window_start: win.start, window_end: win.end,
      max_attempts: attempts, cooldown_minutes: cooldown, start: true,
    }, {
      onSuccess: (d) => {
        setActiveId(d.id);
        const dropped = d.unowned ? ` · ${d.unowned} not assigned to this pool` : "";
        toast(`Dialing ${d.queued} leads across ${rms.length} RM${rms.length > 1 ? "s" : ""}${dropped}`,
          d.queued ? "blue" : "gold", "📞");
      },
      onError: (e: any) => toast(e.message, "gold", "⚠"),
    });
  }

  const act = (a: "start" | "pause" | "stop") =>
    activeId && action.mutate({ id: activeId, action: a }, {
      onError: (e: any) => toast(e.message, "gold", "⚠"),
    });

  if (meta.isError) {
    return <div className="card dl-empty" style={{ padding: 28 }}>
      {(meta.error as Error).message === "admin only"
        ? "The auto dialer is admin-only — it rings other people's phones."
        : (meta.error as Error).message}
    </div>;
  }

  return (
    <div className="dl-page">
      <div className="dl-head">
        <input className="dl-nameinput" value={name} onChange={(e) => setName(e.target.value)}
          placeholder="Name this campaign…" maxLength={120} disabled={!!activeId} />
        <span className="dl-matchchip">
          {preview.isFetching ? "counting…"
            : scoped ? `${matched} leads to call` : `${matched} leads matched`}
        </span>
        <div className="dl-spacer" />
        {!activeId ? (
          <button className="btn primary" onClick={launch}
            disabled={createCampaign.isPending || !name.trim()}
            title={name.trim() ? "" : "Name the campaign first"}>
            {createCampaign.isPending ? "Starting…" : "Start dialing"}
          </button>
        ) : (
          <>
            <button className="btn" onClick={() => act(running ? "pause" : "start")}>
              {running ? "Pause" : "Resume"}
            </button>
            <button className="btn" onClick={() => act("stop")}>Stop</button>
            <button className="btn" onClick={resetForm}>New campaign</button>
          </>
        )}
      </div>

      <div className="dl-layout">
        <main className="dl-main">
          <section className="card">
            <div className="dl-cardhead">
              <div><div className="dl-eyebrow">Step 1</div><h2 className="dl-cardtitle">Who gets called</h2></div>
              <span className="dl-count">
                <b>{matched}</b> {scoped ? "assigned to this pool" : "leads"}
              </span>
            </div>
            {meta.isLoading ? <div className="dl-empty">Loading fields…</div>
              : <Group node={tree} fields={fields} depth={0} update={update} remove={remove} addChild={addChild} />}
            <p className="dl-note">
              Leads with no phone number, and test rows, are never dialled whatever the rules say.
              {preview.isError && <> · <span className="dl-bad">{(preview.error as Error).message}</span></>}
            </p>
          </section>

          <section className="card">
            <div className="dl-cardhead">
              <div><div className="dl-eyebrow">Step 2</div><h2 className="dl-cardtitle">Who calls them</h2></div>
            </div>
            <div className="dl-strat">
              {STRATEGIES.map((s) => (
                <button key={s.key} className={"dl-stratcard" + (strategy === s.key ? " on" : "")}
                  onClick={() => setStrategy(s.key)} disabled={!!activeId}>
                  <span className="dl-stratlabel">{s.label}</span>
                  <span className="dl-strathint">{s.hint}</span>
                </button>
              ))}
            </div>
            <div className="dl-rmpool">
              {pool.map((r) => {
                const on = rms.includes(r.email);
                return (
                  <button key={r.email} className={"dl-rmchip" + (on ? " on" : "")}
                    disabled={!!activeId || !r.has_phone}
                    title={r.has_phone ? r.email : "No mobile number on file — can't be dialled"}
                    onClick={() => setRms(on ? rms.filter((e) => e !== r.email) : [...rms, r.email])}>
                    <span className="dl-avatar">{r.name[0]?.toUpperCase()}</span>
                    <span className="dl-rmmeta">
                      <b>{r.name}</b>
                      <span>{r.has_phone ? r.email : "no mobile on file"}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="dl-note">
              {rms.length || "No"} RM{rms.length === 1 ? "" : "s"} selected — that's{" "}
              <b>{rms.length} call{rms.length === 1 ? "" : "s"} at a time</b>, one per handset.
              Their phone rings first; the lead is only dialled once they pick up.
              {strategy === "assigned" && <>
                {" "}Each RM only calls their own leads, so a matched lead assigned to
                nobody here is dropped when the campaign starts.
              </>}
            </p>
          </section>

          <section className="card">
            <div className="dl-cardhead">
              <div><div className="dl-eyebrow">Step 3</div><h2 className="dl-cardtitle">Pacing</h2></div>
            </div>
            <div className="dl-settings">
              <label className="dl-field"><span>Gap between calls (seconds)</span>
                <input type="number" min={0} max={3600} className="dl-input" value={gap}
                  disabled={!!activeId} onChange={(e) => setGap(Math.max(0, Number(e.target.value)))} />
                <em className="dl-hint">0 = the next lead rings the moment the last call ends</em>
              </label>
              <label className="dl-field"><span>Calling window (IST)</span>
                <div className="dl-daterow">
                  <input type="time" className="dl-input" value={win.start} disabled={!!activeId}
                    onChange={(e) => setWin({ ...win, start: e.target.value })} />
                  <span className="dl-dash">–</span>
                  <input type="time" className="dl-input" value={win.end} disabled={!!activeId}
                    onChange={(e) => setWin({ ...win, end: e.target.value })} />
                </div>
              </label>
              <label className="dl-field"><span>Max attempts / lead</span>
                <input type="number" min={1} max={10} className="dl-input" value={attempts}
                  disabled={!!activeId} onChange={(e) => setAttempts(Math.max(1, Number(e.target.value)))} />
                <em className="dl-hint">Retries only leads that never connected</em>
              </label>
              <label className="dl-field"><span>Cooldown before a retry (minutes)</span>
                <input type="number" min={0} className="dl-input" value={cooldown}
                  disabled={!!activeId || attempts < 2}
                  onChange={(e) => setCooldown(Math.max(0, Number(e.target.value)))} />
              </label>
            </div>
          </section>
        </main>

        <aside className="dl-side">
          <div className="card dl-livecard">
            <div className="dl-livehead">
              <span className={"dl-livedot" + (running ? " on" : "")} />
              {live ? (running ? "Dialing live" : `Campaign ${live.campaign.status}`) : "Idle"}
            </div>
            <div className="dl-stats">
              <div className="dl-stat"><b>{stats?.pending ?? 0}</b><span>In queue</span></div>
              <div className="dl-stat"><b>{stats?.live ?? 0}</b><span>On call</span></div>
              <div className="dl-stat"><b>{(stats?.done ?? 0) + (stats?.failed ?? 0)}</b><span>Done</span></div>
            </div>
            {/* With retries on, "done" undercounts the dialling: one lead can be rung
                several times. Only shown once a repeat has actually happened. */}
            {!!stats && stats.total_calls > stats.unique_leads && (
              <div className="dl-note" style={{ marginTop: 8 }}>
                {stats.unique_leads} unique lead{stats.unique_leads === 1 ? "" : "s"} called ·{" "}
                <b>{stats.total_calls} calls placed</b>
              </div>
            )}
          </div>

          <div className="card">
            <div className="dl-eyebrow">Relationship managers</div>
            <div className="dl-rmlist">
              {(live?.campaign.rms || rms).map((email) => {
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
              {!rms.length && !live && <div className="dl-empty">Pick RMs in Step 2.</div>}
            </div>
          </div>

          <div className="card">
            <div className="dl-eyebrow">Recent calls</div>
            <div className="dl-feed">
              {!live?.feed.length && <div className="dl-empty">No calls yet.</div>}
              {live?.feed.map((r) => (
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

          {!!campaigns.data?.items.length && (
            <div className="card">
              <div className="dl-eyebrow">Campaigns</div>
              <div className="dl-rmlist">
                {campaigns.data.items.map((c) => (
                  <button key={c.id} className={"dl-camprow" + (c.id === activeId ? " on" : "")}
                    onClick={() => setActiveId(c.id)}>
                    <div className="dl-rmmeta">
                      <b>{c.name}</b>
                      <span>{c.status} · {c.completed}/{c.total}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
