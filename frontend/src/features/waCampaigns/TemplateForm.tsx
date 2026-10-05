/* Add / edit one WhatsApp template (spec §4.1, §9). Portaled to <body> and on useModalExit —
   the same shape as LeadDetail's QualifyModal — so Escape closes only this, and the topbar's
   backdrop-filter can't trap a modal opened from it.

   The body is the approved text and nothing else: Gupshup only ever receives the template id
   and the variable values. The slot count is DERIVED from the body (never typed), by the same
   rule as the server (`templateVars`), so the form can say a slot is missing or out of order
   before a round trip does. Once ANY campaign references the template (a draft counts — that is
   `used`, not "was sent"), its body and Gupshup id are locked. */
import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isGupshupTemplateId, slotRe, templateVars, WaTemplate, WaTemplateIn } from "../../lib/api";
import { useSaveWaTemplate } from "../../lib/queries";
import { useModalExit } from "../../lib/useModalExit";
import { useToast } from "../../components/Toast";
import { IconX } from "../../components/icons";

// shown under BOTH locked fields — one string, so the two can't drift apart
const LOCK_HINT = "Used by a campaign — the text and Gupshup ID are locked. To change them, deactivate this one and add a new one (it can reuse the same Gupshup ID).";

export default function TemplateForm({ t, onClose: rawClose }: { t?: WaTemplate; onClose: () => void }) {
  const { onClose, overlayClass } = useModalExit(rawClose);
  const save = useSaveWaTemplate();
  const toast = useToast();
  /* Close on a click on the dark overlay ONLY if the press began there too. A text-selection drag
     that starts in the body box and ends outside the modal fires `click` on the overlay (the common
     ancestor of the two ends); closing on that threw away a pasted template body. */
  const pressedOverlay = useRef(false);
  const [f, setF] = useState<WaTemplateIn>({
    gupshup_template_id: t?.gupshup_template_id ?? "", name: t?.name ?? "", language: t?.language ?? "en",
    category: t?.category ?? "MARKETING", body: t?.body ?? "", variable_labels: t?.variable_labels ?? [],
    variable_defaults: t?.variable_defaults ?? [], buttons: t?.buttons ?? [], active: t?.active ?? true,
  });
  /* The buttons box keeps what was TYPED. Showing `buttons.join(", ")` while splitting on every
     keystroke rewrites the box under the cursor — each comma gains a space and Backspace can't
     remove a trailing ", ". `f.buttons` is the split of this text; the server strips each one
     and drops the blanks. */
  const [buttonsText, setButtonsText] = useState(() => (t?.buttons ?? []).join(", "));
  const n = templateVars(f.body);
  const idOk = isGupshupTemplateId(f.gupshup_template_id);
  const locked = !!t?.used;
  const set = <K extends keyof WaTemplateIn>(k: K, v: WaTemplateIn[K]) => setF((p) => ({ ...p, [k]: v }));
  const slot = (arr: (string | null)[], i: number, v: string) => { const a = [...arr]; a[i] = v; return a; };
  const preview = f.body.replace(slotRe(), (_, d) => `‹${f.variable_labels[Number(d) - 1] || `Variable ${d}`}›`);
  const submit = () => save.mutate({ id: t?.id, t: { ...f,
    variable_labels: Array.from({ length: n }, (_, i) => f.variable_labels[i] ?? ""),
    variable_defaults: Array.from({ length: n }, (_, i) => f.variable_defaults[i] || null) } }, {
    onSuccess: () => { toast(t ? "Template updated" : "Template added", "green"); onClose(); },
    onError: (e: any) => toast(e.message, "gold"),
  });
  return createPortal(
    <div className={overlayClass}
      onMouseDown={(e) => { pressedOverlay.current = e.target === e.currentTarget; }}
      onClick={(e) => {
        const away = pressedOverlay.current && e.target === e.currentTarget;
        pressedOverlay.current = false;
        if (away) onClose();
      }}>
      <div className="modal" style={{ width: "min(640px,100%)" }} role="dialog" aria-label="Template">
        <div className="mh"><h3>{t ? `Edit ${t.name}` : "Add template"}</h3>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}><IconX /></button></div>
        <div className="mb">
          <div className="two">
            <div className="field"><label htmlFor="tf-gid">Gupshup template ID</label>
              <input id="tf-gid" value={f.gupshup_template_id} disabled={locked} placeholder="7c1f3b2a-5d1e-4a8b-9c0f-…"
                onChange={(e) => set("gupshup_template_id", e.target.value)} />
              <div className={"wc-hint" + (!locked && f.gupshup_template_id.trim() && !idOk ? " bad" : "")}>
                {locked ? LOCK_HINT
                  : f.gupshup_template_id.trim() && !idOk ? "That isn't a Gupshup template ID — copy the long ID from Gupshup → Templates, not the template's name."
                  : "From Gupshup → Templates (the long ID, not the name)."}</div></div>
            <div className="field"><label htmlFor="tf-name">Name</label>
              <input id="tf-name" value={f.name} onChange={(e) => set("name", e.target.value)} /></div>
          </div>
          <div className="two">
            <div className="field"><label htmlFor="tf-lang">Language</label>
              <input id="tf-lang" value={f.language} onChange={(e) => set("language", e.target.value)} /></div>
            <div className="field"><label htmlFor="tf-cat">Category</label>
              <select id="tf-cat" value={f.category ?? ""} onChange={(e) => set("category", e.target.value || null)}>
                <option value="MARKETING">Marketing</option><option value="UTILITY">Utility</option></select></div>
          </div>
          <div className="field"><label htmlFor="tf-body">Body — exactly the approved text, with {"{{1}}"} slots</label>
            <textarea id="tf-body" rows={4} value={f.body} disabled={locked} onChange={(e) => set("body", e.target.value)} />
            <div className={"wc-hint" + (n < 0 ? " bad" : "")}>
              {locked ? LOCK_HINT
                : n < 0 ? "Slots must first appear in order — {{1}}, then {{2}}, … — with no gap and no {{0}} (Gupshup fills them in the order they occur)."
                : `Detected ${n} variable${n === 1 ? "" : "s"} · text templates only (an image, video or document header isn't supported, nor is a variable in a header — Gupshup doesn't document how those are ordered)`}</div></div>
          {Array.from({ length: Math.max(n, 0) }, (_, i) => (
            <div className="two" key={i}>
              <div className="field"><label htmlFor={`tf-lbl-${i}`}>{`{{${i + 1}}}`} label</label>
                <input id={`tf-lbl-${i}`} value={f.variable_labels[i] ?? ""} placeholder={i === 0 ? "Name" : "City"}
                  onChange={(e) => set("variable_labels", slot(f.variable_labels, i, e.target.value) as string[])} /></div>
              <div className="field"><label htmlFor={`tf-def-${i}`}>Fallback if blank (optional)</label>
                <input id={`tf-def-${i}`} value={f.variable_defaults[i] ?? ""} placeholder={i === 0 ? "there" : ""}
                  onChange={(e) => set("variable_defaults", slot(f.variable_defaults, i, e.target.value))} /></div>
            </div>))}
          <div className="field"><label htmlFor="tf-btn">Quick-reply buttons (comma-separated)</label>
            <input id="tf-btn" value={buttonsText} placeholder="Yes, No"
              onChange={(e) => { setButtonsText(e.target.value); set("buttons", e.target.value.split(",")); }} /></div>
          <label className="wc-check"><input type="checkbox" checked={f.active}
            onChange={(e) => set("active", e.target.checked)} /> Active</label>
          {f.body && <div className="wc-preview">{preview}</div>}
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={save.isPending || n < 0 || !f.body.trim() || !f.name.trim() || !idOk}
            onClick={submit}>{save.isPending ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </div>, document.body);
}
