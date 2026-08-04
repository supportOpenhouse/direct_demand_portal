/* Schedule Campaign — build a queue from a rule tree and hand it to a pool of RMs.

   Compose-only. Nothing dials from this page and nothing is monitored here: on launch
   it hands off to Previous Campaigns, which owns the live panel, the per-RM state and
   the Pause/Stop controls. A loop on the server places the calls and the Bonvoice
   hangup callback is what frees an RM for the next lead. Closing the tab stops nothing.

   Concurrency is the size of the pool: Click2Call rings the RM's own handset first, so
   one RM can only ever hold one live call. Three RMs = three calls at a time — which is
   why the server refuses to run two campaigns that share an RM at overlapping hours. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateCampaign, useDialerFields, useRulePreview } from "../lib/queries";
import { DialerField, RuleGroup, RuleNode, RuleValue } from "../lib/api";
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

/* What a brand-new campaign starts as. Kept in one place so the form can snap back
   to it after a launch — see resetForm. */
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
  const navigate = useNavigate();
  const meta = useDialerFields();
  const createCampaign = useCreateCampaign();

  const [name, setName] = useState(DEFAULTS.name);
  const [tree, setTree] = useState<RuleGroup>(emptyTree);
  const [rms, setRms] = useState<string[]>([]);
  const [strategy, setStrategy] = useState(DEFAULTS.strategy);
  const [gap, setGap] = useState(DEFAULTS.gap);
  const [win, setWin] = useState(DEFAULTS.win);
  const [attempts, setAttempts] = useState(DEFAULTS.attempts);
  const [cooldown, setCooldown] = useState(DEFAULTS.cooldown);

  const fields = meta.data?.fields || [];
  const pool = meta.data?.rms || [];
  const debouncedTree = useDebounce(tree, 350);
  const preview = useRulePreview(debouncedTree, strategy, rms);

  const update = (id: string, patch: Partial<RuleNode>) =>
    setTree((t) => mapTree(t, (n) => (n.id === id ? { ...n, ...patch } as RuleNode : n)) as RuleGroup);
  const remove = (id: string) => setTree((t) => removeById(t, id) as RuleGroup);
  const addChild = (pid: string, child: RuleNode) =>
    setTree((t) => mapTree(t, (n) =>
      n.id === pid && n.type === "group" ? { ...n, children: [...n.children, child] } : n) as RuleGroup);

  const matched = preview.data?.count ?? 0;
  // 'assigned' + a chosen pool: the count is what those RMs own, not every match
  const scoped = !!preview.data?.scoped;

  function resetForm() {
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
        const dropped = d.unowned ? ` · ${d.unowned} not assigned to this pool` : "";
        toast(`Dialing ${d.queued} leads across ${rms.length} RM${rms.length > 1 ? "s" : ""}${dropped}`,
          d.queued ? "blue" : "gold", "📞");
        // Monitoring lives on Previous Campaigns now — leaving them on a spent form
        // with no live panel would just look like nothing happened.
        resetForm();
        navigate("/dialer/previous");
      },
      onError: (e: any) => toast(e.message, "gold", "⚠"),
    });
  }

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
          placeholder="Name this campaign…" maxLength={120} />
        <span className="dl-matchchip">
          {preview.isFetching ? "counting…"
            : scoped ? `${matched} leads to call` : `${matched} leads matched`}
        </span>
        <div className="dl-spacer" />
        <button className="btn primary" onClick={launch}
          disabled={createCampaign.isPending || !name.trim()}
          title={name.trim() ? "" : "Name the campaign first"}>
          {createCampaign.isPending ? "Starting…" : "Start dialing"}
        </button>
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
                  onClick={() => setStrategy(s.key)}>
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
                    disabled={!r.has_phone}
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
                  onChange={(e) => setGap(Math.max(0, Number(e.target.value)))} />
                <em className="dl-hint">0 = the next lead rings the moment the last call ends</em>
              </label>
              <label className="dl-field"><span>Calling window (IST)</span>
                <div className="dl-daterow">
                  <input type="time" className="dl-input" value={win.start}
                    onChange={(e) => setWin({ ...win, start: e.target.value })} />
                  <span className="dl-dash">–</span>
                  <input type="time" className="dl-input" value={win.end}
                    onChange={(e) => setWin({ ...win, end: e.target.value })} />
                </div>
              </label>
              <label className="dl-field"><span>Max attempts / lead</span>
                <input type="number" min={1} max={10} className="dl-input" value={attempts}
                  onChange={(e) => setAttempts(Math.max(1, Number(e.target.value)))} />
                <em className="dl-hint">Retries only leads that never connected</em>
              </label>
              <label className="dl-field"><span>Cooldown before a retry (minutes)</span>
                <input type="number" min={0} className="dl-input" value={cooldown}
                  disabled={attempts < 2}
                  onChange={(e) => setCooldown(Math.max(0, Number(e.target.value)))} />
              </label>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
