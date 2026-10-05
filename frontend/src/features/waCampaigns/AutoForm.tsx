/* Add / edit one auto-campaign definition (spec §7). Portaled to <body> on useModalExit, like TemplateForm.

   Dry run shows who the NEXT run would message under the form's CURRENT values — POST /auto/dry-run takes them in
   the body, uses the same list-building code a real run uses, and writes nothing (no definition, no campaign), so
   it is safe on a new form, on a live definition, and on edits nobody has saved.
   Save keeps a new definition inactive; the Active switch on the tab is what turns it on. */
import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { IconX } from "../../components/icons";
import { useToast } from "../../components/Toast";
import { WaAuto, WaAutoDryRun, WaAutoIn } from "../../lib/api";
import { useSaveWaAuto, useWaCampaign, useWaCampaigns, useWaTemplates } from "../../lib/queries";
import { useModalExit } from "../../lib/useModalExit";
import { WA_COOLDOWN_DAYS } from "./NewCampaign";
import { api } from "../../lib/api";

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
// tomorrow on the IST calendar — a UTC date would be yesterday's before 05:30 IST
const tomorrowIST = () =>
  new Date(Date.now() + 864e5).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
const COUNT_LABEL: [string, string][] = [["valid", "Would send"], ["skipped", "Skipped"], ["invalid", "Invalid"], ["duplicate", "Duplicate"]];

export default function AutoForm({ a, seedId, onClose: rawClose }: { a?: WaAuto; seedId?: string | null; onClose: () => void }) {
  const { onClose, overlayClass } = useModalExit(rawClose);
  const save = useSaveWaAuto();
  const toast = useToast();
  const templates = useWaTemplates();
  const campaigns = useWaCampaigns();
  const pressedOverlay = useRef(false);
  const manual = (campaigns.data?.items ?? []).filter((c) => c.source !== "auto" && !c.auto_campaign_id && c.status !== "draft");
  const seed = seedId ? manual.find((c) => c.id === seedId) : undefined;
  const tplItems = templates.data?.items ?? [];

  const [f, setF] = useState<WaAutoIn>(() => ({
    name: a?.name ?? "", template_id: a?.template_id ?? "", seed_campaign_id: a?.seed_campaign_id ?? seedId ?? "",
    repeat_mode: a?.repeat_mode ?? "non_responders", every_days: a?.every_days ?? 1, run_at: a?.run_at ?? "11:00",
    start_on: a?.next_slot ?? tomorrowIST(), cooldown_days: a?.cooldown_days ?? WA_COOLDOWN_DAYS, max_runs: a?.max_runs ?? null,
    send_window_start: a?.send_window_start ?? "10:00", send_window_end: a?.send_window_end ?? "19:00",
    rate_per_minute: a?.rate_per_minute ?? 30,
  }));
  // the select lists only the newest 200 campaigns: a seed older than that (or one just opened by link) must still
  // show, labelled with its own name, or the form looks unseeded while seed_campaign_id is set
  const missingSeed = !!f.seed_campaign_id && !manual.some((c) => c.id === f.seed_campaign_id);
  const seedDetail = useWaCampaign(missingSeed ? f.seed_campaign_id : "");
  const seedName = seedDetail.data?.campaign.name ?? (seedDetail.isError ? "(campaign not found)" : "Loading…");
  const set = <K extends keyof WaAutoIn>(k: K, v: WaAutoIn[K]) => setF((p) => ({ ...p, [k]: v }));
  // `?seed=` arrives before the lists load: fill the name and template once they are in, only into blanks
  const [seeded, setSeeded] = useState(false);
  if (!a && seed && !seeded && (templates.data || !seed.template_name)) {
    setSeeded(true);
    setF((p) => ({ ...p, name: p.name || `${seed.name} (auto)`,
      template_id: p.template_id || tplItems.find((t) => t.name === seed.template_name)?.id || "" }));
  }

  const [dry, setDry] = useState<WaAutoDryRun | null>(null);
  const [dryBusy, setDryBusy] = useState(false);
  const [dryErr, setDryErr] = useState<string | null>(null);
  const changed = (fn: () => void) => { fn(); setDry(null); };   // a result for the old settings would mislead

  const winOk = HHMM.test(f.send_window_start) && HHMM.test(f.send_window_end) && f.send_window_start < f.send_window_end;
  const ok = !!f.name.trim() && !!f.template_id && !!f.seed_campaign_id && HHMM.test(f.run_at) && !!f.start_on
    && f.every_days >= 1 && f.every_days <= 90 && f.cooldown_days >= 0 && f.rate_per_minute >= 1 && winOk
    && (f.max_runs == null || f.max_runs >= 1);

  const submit = () => save.mutateAsync({ id: a?.id, body: f }).then(() => { toast(a ? "Auto campaign updated" : "Auto campaign saved — switch it on from the list", "green"); onClose(); })
    .catch((e: any) => toast(e.message, "gold"));
  const runDry = async () => {
    setDryBusy(true); setDryErr(null);
    try { setDry(await api.waAutoDryRun(f)); }
    catch (e: any) { setDryErr(e.message); }
    finally { setDryBusy(false); }
  };

  return createPortal(
    <div className={overlayClass}
      onMouseDown={(e) => { pressedOverlay.current = e.target === e.currentTarget; }}
      onClick={(e) => {
        const away = pressedOverlay.current && e.target === e.currentTarget;
        pressedOverlay.current = false;
        if (away) onClose();
      }}>
      <div className="modal" style={{ width: "min(640px,100%)", position: "relative" }} role="dialog" aria-label="Auto campaign">
        <div className="mh"><h3>{a ? `Edit ${a.name}` : "New auto campaign"}</h3>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}><IconX /></button></div>
        <div className="mb">
          <div className="field"><label htmlFor="af-name">Name</label>
            <input id="af-name" value={f.name} onChange={(e) => set("name", e.target.value)} /></div>
          <div className="two">
            <div className="field"><label htmlFor="af-seed">Seed campaign — its list is what repeats</label>
              <select id="af-seed" value={f.seed_campaign_id} disabled={!!a} onChange={(e) => changed(() => set("seed_campaign_id", e.target.value))}>
                <option value="">Choose a campaign…</option>
                {missingSeed && <option value={f.seed_campaign_id}>{seedName}</option>}
                {manual.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              {a && <div className="wc-hint">The seed can't change once the definition exists.</div>}</div>
            <div className="field"><label htmlFor="af-tpl">Template</label>
              <select id="af-tpl" value={f.template_id} onChange={(e) => changed(() => set("template_id", e.target.value))}>
                <option value="">Choose a template…</option>
                {tplItems.filter((t) => t.active || t.id === f.template_id).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select></div>
          </div>
          <div className="field"><label>Each run messages</label>
            <div className="wc-radios">
              <label className="wc-check"><input type="radio" name="auto-repeat" checked={f.repeat_mode === "non_responders"}
                onChange={() => changed(() => set("repeat_mode", "non_responders"))} /> Non-responders only</label>
              <label className="wc-check"><input type="radio" name="auto-repeat" checked={f.repeat_mode === "everyone"}
                onChange={() => changed(() => set("repeat_mode", "everyone"))} /> Everyone on the list</label>
            </div></div>
          <div className="two">
            <div className="field"><label htmlFor="af-every">Every N days</label>
              <input id="af-every" type="number" min={1} max={90} value={f.every_days}
                onChange={(e) => changed(() => set("every_days", Number(e.target.value)))} /></div>
            <div className="field"><label htmlFor="af-at">At (IST)</label>
              <input id="af-at" type="time" value={f.run_at} onChange={(e) => set("run_at", e.target.value)} /></div>
          </div>
          <div className="two">
            <div className="field"><label htmlFor="af-start">{a ? "Next run on" : "Starting on"}</label>
              <input id="af-start" type="date" value={f.start_on} onChange={(e) => set("start_on", e.target.value)} /></div>
            <div className="field"><label htmlFor="af-max">Max runs (blank = no limit)</label>
              <input id="af-max" type="number" min={1} value={f.max_runs ?? ""}
                onChange={(e) => set("max_runs", e.target.value === "" ? null : Number(e.target.value))} /></div>
          </div>
          <div className="two">
            <div className="field"><label htmlFor="af-cool">Skip anyone messaged in the last N days</label>
              <input id="af-cool" type="number" min={0} value={f.cooldown_days}
                onChange={(e) => changed(() => set("cooldown_days", Number(e.target.value)))} />
              <div className="wc-hint">Earlier runs of this same auto campaign don't count — "Every N days" governs those.</div></div>
            <div className="field"><label htmlFor="af-rate">Per minute</label>
              <input id="af-rate" type="number" min={1} value={f.rate_per_minute} onChange={(e) => set("rate_per_minute", Number(e.target.value))} /></div>
          </div>
          <div className="two">
            <div className="field"><label htmlFor="af-ws">Send window from</label>
              <input id="af-ws" type="time" value={f.send_window_start} onChange={(e) => set("send_window_start", e.target.value)} /></div>
            <div className="field"><label htmlFor="af-we">to</label>
              <input id="af-we" type="time" value={f.send_window_end} onChange={(e) => set("send_window_end", e.target.value)} />
              {!winOk && <div className="wc-hint bad">The window must start before it ends.</div>}</div>
          </div>
          {dryErr && <div className="wc-hint bad">{dryErr}</div>}
          {dry && (
            <div className="wc-results">
              {dry.over_daily_limit && (
                <div className="wc-hint" style={{ marginTop: 0, color: "var(--amber)" }} role="alert">
                  Warning — this run is bigger than the daily limit of {dry.daily_limit.toLocaleString("en-IN")} messages.
                </div>
              )}
              <div className="wc-hint" style={{ marginTop: 0 }}>
                Next run would message — {COUNT_LABEL.map(([k, label]) => `${label} ${(dry.counts[k as keyof typeof dry.counts] ?? 0).toLocaleString("en-IN")}`).join(" · ")}
              </div>
              {dry.samples.map((s, i) => <div className="wc-preview" key={i}>{s}</div>)}
            </div>
          )}
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={!ok || dryBusy || save.isPending} onClick={runDry}
            title="Shows who the next run would message with the settings above. Nothing is saved and nothing is sent.">
            {dryBusy ? "Checking…" : "Dry run"}</button>
          <button className="btn primary" disabled={!ok || save.isPending || dryBusy} onClick={submit}>{save.isPending ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </div>, document.body);
}
