/* Topbar "Add lead" — a lead added by hand.

   Who owns it is decided SERVER-side from the signed-in role: an RM keeps the lead,
   an admin's goes to the same round-robin pick the hourly sweep makes (an RM covering
   the city, else the least-loaded RM today). The form only says which will happen.

   A number that is already a lead is not duplicated — the server merges this arrival
   into it (like any other source) and we open that lead instead. */
import { useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "./AuthContext";
import { useToast } from "./Toast";
import { useOpenLead } from "./LeadModal";
import { IconPlus, IconWarn, IconX } from "./icons";
import { useCreateLead } from "../lib/queries";
import { CITIES } from "../lib/leads";
import { isCallingRm } from "../lib/roles";
import { useModalExit } from "../lib/useModalExit";
import type { NewLead } from "../lib/api";

const EMPTY: NewLead = {
  name: "", phone: "", city: "", society: "", budget_band: "", configuration: "", source_remarks: "",
};

export function AddLeadButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="btn sm" onClick={() => setOpen(true)}><IconPlus /> Add lead</button>
      {open && <AddLeadModal onClose={() => setOpen(false)} />}
    </>
  );
}

function AddLeadModal({ onClose: rawClose }: { onClose: () => void }) {
  const { onClose, overlayClass } = useModalExit(rawClose);
  const { enabled, user } = useAuth();
  const rm = enabled && isCallingRm(user?.role);
  const create = useCreateLead();
  const toast = useToast();
  const openLead = useOpenLead();
  const [f, setF] = useState<NewLead>(EMPTY);
  const [err, setErr] = useState(false);

  // the server keeps the last 10 digits (+91 / 0 prefixes are fine); fewer can't be a number
  const phoneOk = f.phone.replace(/\D/g, "").length >= 10;
  const nameOk = !!f.name.trim();

  const submit = () => {
    if (!nameOk || !phoneOk) { setErr(true); return; }
    create.mutate(f, {
      onSuccess: (r) => {
        if (r.created) {
          toast(r.assigned_to ? `Lead added · assigned to ${r.assigned_to}` : "Lead added · no active RM to assign", "green");
        } else {
          toast("That number is already a lead — merged into it", "blue");
        }
        onClose();
        if (r.lead_id) openLead(r.lead_id);
      },
      onError: (e: any) => toast(e.message, "gold"),
    });
  };

  const input = (label: string, key: keyof NewLead, placeholder = "", required = false, bad = false) => (
    <div className={"field" + (bad ? " invalid" : "")}>
      <label>{label}{required && <> <span className="req">*</span></>}</label>
      <input value={f[key]} placeholder={placeholder} onChange={(e) => setF({ ...f, [key]: e.target.value })} />
    </div>
  );

  /* Portalled to <body>. The button lives in the topbar, and `.topbar` has
     backdrop-filter — which makes it the containing block for position:fixed
     descendants. Rendered in place, the "full-screen" overlay was fixed to the 60px
     topbar: the modal centred on it and ran off the top of the viewport. */
  return createPortal(
    <div className={overlayClass} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="mh"><h3>Add lead</h3><div className="icon-btn" onClick={onClose}><IconX /></div></div>
        <div className="mb">
          <div className="two">
            {input("Name", "name", "Buyer's name", true, err && !nameOk)}
            {input("Phone", "phone", "+91 98765 43210", true, err && !phoneOk)}
          </div>
          <div className="two">
            <div className="field"><label>City</label>
              <select value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}>
                <option value="">Select…</option>
                {CITIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            {input("Society of interest", "society")}
          </div>
          <div className="two">
            {input("Budget", "budget_band", "e.g. ₹70L – ₹90L")}
            {input("Configuration", "configuration", "e.g. 3 BHK")}
          </div>
          <div className="field" style={{ marginBottom: 0 }}><label>Remarks</label>
            <textarea rows={2} value={f.source_remarks} onChange={(e) => setF({ ...f, source_remarks: e.target.value })} />
          </div>
          {err && (!nameOk || !phoneOk) && (
            <div className="mand-flag show"><IconWarn /> A name and a 10-digit phone number are required.</div>
          )}
          <div className="add-lead-owner">
            {rm
              ? <>Assigned to <b>you</b>.</>
              : <>Assigned automatically — to an RM covering the city, otherwise the RM with the fewest leads today.</>}
          </div>
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={submit} disabled={create.isPending}>
            {create.isPending ? "Adding…" : "Add lead"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
