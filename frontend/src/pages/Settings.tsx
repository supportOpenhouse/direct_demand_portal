/* Settings & Access — user management. Only people added here can sign in, and
   each maps to their leads via the sheet's "Assigned to" name. */
import { useState } from "react";
import { useAppSettings, useSetAppSetting, useUsers, useUserMutations } from "../lib/queries";
import { api, ManagedUser } from "../lib/api";
import { useToast } from "../components/Toast";
import { useAuth } from "../components/AuthContext";

const ROLES = [
  { v: "admin", label: "Admin", desc: "All leads · manage users & source data" },
  { v: "rm", label: "Relationship Manager", desc: "Own assigned leads only" },
  { v: "test_rm", label: "Test RM", desc: "Same as an RM, tagged TEST in the dialer · never assigned WhatsApp conversations" },
];
const roleLabel = (r: string) => ROLES.find((x) => x.v === r)?.label || r;

/* Org-wide privacy switches. Set here rather than per-browser because it's a PII
   decision — one person makes it for everyone, and an RM can't quietly opt out. */
function PrivacyPanel() {
  const { data, isLoading } = useAppSettings();
  const set = useSetAppSetting();
  const toast = useToast();
  const on = !!data?.hide_lead_phones;

  const flip = () =>
    set.mutate(
      { key: "hide_lead_phones", value: !on },
      {
        onSuccess: () => {
          toast(on ? "Lead numbers are visible again — reloading…"
                   : "Lead numbers hidden in tables — reloading…",
                on ? "blue" : "green", on ? "👁" : "🙈");
          // Hard reload rather than a cache invalidation. This flag decides whether
          // PII is on screen, so every list has to be rebuilt from scratch — a stale
          // render left anywhere is the exact failure the setting exists to prevent.
          // Delayed so the toast is readable before the page goes.
          setTimeout(() => window.location.reload(), 900);
        },
        onError: (e: any) => toast(e.message, "gold", "⚠"),
      },
    );

  return (
    <div className="card panel-pad" style={{ marginTop: 16 }}>
      <div className="section-head">
        <div>
          <div className="panel-title" style={{ marginBottom: 2 }}>Privacy</div>
          <p className="sec-sub" style={{ margin: 0 }}>Applies to everyone, not just you.</p>
        </div>
      </div>
      <div className="set-row">
        <div>
          <div className="set-name">Hide lead phone numbers in tables</div>
          <p className="set-desc">
            Keeps numbers off New Leads, Call Not Received, Follow Up and the segment
            lists — for shared screens, screenshots and demos. Calling, WhatsApp and the
            lead detail page are unaffected.
          </p>
        </div>
        {/* aria-checked + role make this a real switch to a screen reader; without
            them it's an anonymous div that announces nothing. */}
        {/* .switch (app.css) draws the knob with ::after — no child element needed */}
        <button
          role="switch"
          aria-checked={on}
          aria-label="Hide lead phone numbers in tables"
          className={"switch" + (on ? " on" : "")}
          disabled={isLoading || set.isPending}
          onClick={flip}
        />
      </div>
    </div>
  );
}
const initials = (n: string | null, e: string) =>
  (n || e).split(/[ @]/).map((x) => x[0]).slice(0, 2).join("").toUpperCase();

function AddUserForm({ onClose }: { onClose: () => void }) {
  const { create } = useUserMutations();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("rm");
  const [smid, setSmid] = useState("");
  const [phone, setPhone] = useState("");

  const submit = () => {
    if (!email.trim() || !name.trim()) {
      toast("Email and name are required", "gold", "⚠");
      return;
    }
    create.mutate(
      { email: email.trim(), name: name.trim(), role, smid: smid.trim() ? Number(smid) : null,
        phone: phone.trim() || null },
      {
        onSuccess: () => {
          toast(`${name} added`, "green", "✓");
          onClose();
        },
        onError: (e: any) => toast(e.message, "gold", "⚠"),
      }
    );
  };

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="mh">
          <h3>Add a user</h3>
          <div className="icon-btn" onClick={onClose}>✕</div>
        </div>
        <div className="mb">
          <div className="note" style={{ marginBottom: 16 }}>
            They sign in with this Google account — nobody else can log in. Their leads are mapped automatically
            from the sheet's <b>Assigned to</b> column by matching their name (first or full).
          </div>
          <div className="field">
            <label>Google email <span className="req">*</span></label>
            <input type="email" value={email} placeholder="name@openhouse.in" onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="field">
            <label>Full name <span className="req">*</span></label>
            <input value={name} placeholder="e.g. Dheeraj Kumar" onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="two">
            <div className="field">
              <label>Role</label>
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                {ROLES.map((r) => <option key={r.v} value={r.v}>{r.label}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Openhouse SMID <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— to book visits</span></label>
              <input type="number" value={smid} placeholder="e.g. 82" onChange={(e) => setSmid(e.target.value)} />
            </div>
          </div>
          <div className="field">
            <label>Mobile <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— rings first on click-to-call</span></label>
            <input value={phone} placeholder="e.g. 98765 43210" onChange={(e) => setPhone(e.target.value)} />
          </div>
          <div className="note" style={{ marginTop: 0 }}>
            {ROLES.find((r) => r.v === role)?.desc}
            {name.trim() && <> · maps leads assigned to <b>{name.trim().split(" ")[0]}</b></>}
            <> · SMID is their Openhouse SalesManager id — required to book visits</>
          </div>
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn green" onClick={submit} disabled={create.isPending}>
            {create.isPending ? "Adding…" : "Add user"}
          </button>
        </div>
      </div>
    </div>
  );
}

function EditUserForm({ u, onClose }: { u: ManagedUser; onClose: () => void }) {
  const { update } = useUserMutations();
  const toast = useToast();
  const [name, setName] = useState(u.name || "");
  const [role, setRole] = useState(u.role);
  const [smid, setSmid] = useState(u.smid != null ? String(u.smid) : "");
  const [phone, setPhone] = useState(u.phone ?? "");

  const submit = () => {
    if (!name.trim()) {
      toast("Name is required", "gold", "⚠");
      return;
    }
    update.mutate(
      { id: u.id, patch: { name: name.trim(), role, smid: smid.trim() ? Number(smid) : null,
        phone: phone.trim() || null } },
      { onSuccess: () => { toast("User updated", "green", "✓"); onClose(); }, onError: (e: any) => toast(e.message, "gold", "⚠") }
    );
  };

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="mh">
          <h3>Edit {u.name || u.email}</h3>
          <div className="icon-btn" onClick={onClose}>✕</div>
        </div>
        <div className="mb">
          <div className="field"><label>Email</label><input value={u.email} disabled /></div>
          <div className="field"><label>Full name <span className="req">*</span></label>
            <input value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div className="two">
            <div className="field"><label>Role</label>
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                {ROLES.map((r) => <option key={r.v} value={r.v}>{r.label}</option>)}
              </select></div>
            <div className="field"><label>Openhouse SMID <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— to book visits</span></label>
              <input type="number" value={smid} placeholder="e.g. 82" onChange={(e) => setSmid(e.target.value)} /></div>
          </div>
          <div className="field"><label>Mobile <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>— rings first on click-to-call</span></label>
            <input value={phone} placeholder="e.g. 98765 43210" onChange={(e) => setPhone(e.target.value)} /></div>
          <div className="note" style={{ marginTop: 0 }}>
            Mapped to <b>{u.matched_leads}</b> leads by matching <b>{name.trim().split(" ")[0] || u.maps_to}</b> in the sheet's “Assigned to”.
            {smid.trim() ? <> · books visits as SMID <b>{smid.trim()}</b></> : <> · <b>no SMID</b> — can't book visits</>}
          </div>
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn green" onClick={submit} disabled={update.isPending}>{update.isPending ? "Saving…" : "Save changes"}</button>
        </div>
      </div>
    </div>
  );
}

/* Shown before disabling/removing a user who still owns leads — reassign them to
   another active user first so nothing is orphaned. */
function ReassignModal({ u, action, candidates, onClose }: {
  u: ManagedUser; action: "disable" | "remove"; candidates: ManagedUser[]; onClose: () => void;
}) {
  const { update, remove, reassign } = useUserMutations();
  const toast = useToast();
  const [to, setTo] = useState(candidates[0]?.id || "");
  const busy = reassign.isPending || update.isPending || remove.isPending;
  const verb = action === "disable" ? "Disable" : "Remove";

  const doAction = (onDone: () => void) => {
    const opts = { onSuccess: onDone, onError: (e: any) => toast(e.message, "gold", "⚠") };
    if (action === "disable") update.mutate({ id: u.id, patch: { active: false } }, opts);
    else remove.mutate(u.id, opts);
  };

  const reassignThen = () => {
    if (!to) { toast("Pick a user to reassign to", "gold", "⚠"); return; }
    const target = candidates.find((c) => c.id === to);
    reassign.mutate({ id: u.id, toUserId: to }, {
      onSuccess: (r) => doAction(() => {
        toast(`${r.moved} lead${r.moved === 1 ? "" : "s"} → ${target?.name} · ${u.name} ${action === "disable" ? "disabled" : "removed"}`, "green", "✓");
        onClose();
      }),
      onError: (e: any) => toast(e.message, "gold", "⚠"),
    });
  };

  const skip = () => doAction(() => { toast(`${u.name} ${action === "disable" ? "disabled" : "removed"} · leads left as-is`, "blue", "✓"); onClose(); });

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="mh">
          <h3>{verb} {u.name || u.email}</h3>
          <div className="icon-btn" onClick={onClose}>✕</div>
        </div>
        <div className="mb">
          <div className="note" style={{ marginBottom: 16 }}>
            <b>{u.name || u.email}</b> owns <b>{u.matched_leads}</b> lead{u.matched_leads === 1 ? "" : "s"}. Reassign them to another
            user before you {action} — otherwise those leads stay mapped to a {action === "remove" ? "deleted" : "disabled"} owner.
          </div>
          {candidates.length === 0 ? (
            <div className="note">No other active users to reassign to. Add one first, or {action} anyway.</div>
          ) : (
            <div className="field">
              <label>Reassign {u.matched_leads} lead{u.matched_leads === 1 ? "" : "s"} to</label>
              <select value={to} onChange={(e) => setTo(e.target.value)}>
                {candidates.map((c) => <option key={c.id} value={c.id}>{c.name || c.email} · {roleLabel(c.role)}</option>)}
              </select>
            </div>
          )}
        </div>
        <div className="mf" style={{ justifyContent: "space-between" }}>
          <button className="btn ghost sm" onClick={skip} disabled={busy}>{verb} without reassigning</button>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
            {candidates.length > 0 && (
              <button className="btn green" onClick={reassignThen} disabled={busy}>{busy ? "Working…" : `Reassign & ${verb}`}</button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function UserRow({ u, allUsers }: { u: ManagedUser; allUsers: ManagedUser[] }) {
  const { update, remove } = useUserMutations();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [reassignFor, setReassignFor] = useState<"disable" | "remove" | null>(null);
  const candidates = allUsers.filter((x) => x.active && x.id !== u.id);
  return (
    <div className="role-row" style={{ gap: 14 }}>
      {u.picture ? (
        <img className="av" src={u.picture} alt="" style={{ width: 36, height: 36, borderRadius: 9, objectFit: "cover" }} />
      ) : (
        <div className="av" style={{ width: 36, height: 36, borderRadius: 9, background: "linear-gradient(135deg,#e4e9f1,#d3dbe8)", display: "grid", placeItems: "center", fontWeight: 700, color: "var(--ink-2)", fontSize: 12 }}>
          {initials(u.name, u.email)}
        </div>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13.5 }}>
          {u.name || "—"} {!u.active && <span className="bucket-tag" style={{ background: "var(--coral-soft)", color: "var(--coral)", borderColor: "#f3c6cd" }}>disabled</span>}
        </div>
        <div className="ph" style={{ fontSize: 11.5 }}>{u.email}</div>
      </div>
      <div style={{ textAlign: "center", minWidth: 86 }}>
        <div style={{ fontFamily: "'Bricolage Grotesque'", fontWeight: 800, fontSize: 17, lineHeight: 1 }}>{u.matched_leads}</div>
        <div style={{ fontSize: 10.5, color: "var(--muted)" }}>leads · {u.maps_to}</div>
      </div>
      <select
        value={u.role}
        onChange={(e) => update.mutate({ id: u.id, patch: { role: e.target.value } }, { onSuccess: () => toast("Role updated", "green", "✓") })}
        style={{ border: "1px solid var(--line)", borderRadius: 8, padding: "5px 8px", fontSize: 12, fontWeight: 600, background: "var(--panel-2)" }}
      >
        {ROLES.map((r) => <option key={r.v} value={r.v}>{roleLabel(r.v)}</option>)}
      </select>
      <div className={"switch" + (u.active ? " on" : "")} title={u.active ? "Disable" : "Enable"}
        onClick={() => {
          // disabling an owner with leads → prompt to reassign; enabling or no leads → act directly
          if (u.active && u.matched_leads > 0) setReassignFor("disable");
          else update.mutate({ id: u.id, patch: { active: !u.active } });
        }} />
      <button className="btn ghost sm" onClick={() => setEditing(true)}>✎ Edit</button>
      <button className="btn ghost sm" onClick={() => {
        if (u.matched_leads > 0) setReassignFor("remove");
        else if (confirm(`Remove ${u.name || u.email}?`)) remove.mutate(u.id, { onSuccess: () => toast("User removed", "blue", "✓") });
      }}>Remove</button>
      {editing && <EditUserForm u={u} onClose={() => setEditing(false)} />}
      {reassignFor && <ReassignModal u={u} action={reassignFor} candidates={candidates} onClose={() => setReassignFor(null)} />}
    </div>
  );
}

export default function Settings() {
  const { enabled, user, logout } = useAuth();
  const { data, isLoading } = useUsers();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const isAdmin = !enabled || user?.role === "admin";

  if (!isAdmin) {
    return <div className="card"><div className="empty" style={{ padding: 40 }}>Only admins can manage users.</div></div>;
  }

  // Sign everyone out (self included) — the server invalidates all tokens, then we
  // drop the current session so this admin lands back on the sign-in screen.
  const forceLogout = async () => {
    if (!confirm("Force-log-out ALL users? Everyone — including you — will have to sign in again.")) return;
    setLoggingOut(true);
    try {
      await api.forceLogoutAll();
      toast("All users signed out — redirecting to sign-in…", "green", "✓");
      setTimeout(logout, 1200);
    } catch (e: any) {
      toast(e.message, "gold", "⚠");
      setLoggingOut(false);
    }
  };

  return (
    <>
      {!enabled && (
        <div className="note" style={{ marginBottom: 16 }}>
          Google sign-in isn't configured yet, so the app is open. Set <span className="kbd">VITE_GOOGLE_CLIENT_ID</span> +{" "}
          <span className="kbd">GOOGLE_OAUTH_CLIENT_ID</span> to enforce that only the users below can log in.
        </div>
      )}
      <div className="card panel-pad">
        <div className="section-head">
          <div>
            <div className="panel-title" style={{ marginBottom: 2 }}>Users & access</div>
            <p className="sec-sub" style={{ margin: 0 }}>Each user maps to their leads by the sheet's “Assigned to” name.</p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {enabled && (
              <button className="btn ghost" onClick={forceLogout} disabled={loggingOut}
                style={{ color: "var(--coral)", borderColor: "#f3c6cd" }} title="Invalidate every active session">
                {loggingOut ? "Signing out…" : "⎋ Force logout all"}
              </button>
            )}
            <button className="btn green" onClick={() => setAdding(true)}>+ Add user</button>
          </div>
        </div>
        {isLoading ? (
          <div className="empty" style={{ padding: 30 }}>Loading users…</div>
        ) : !data?.items.length ? (
          <div className="empty" style={{ padding: 30 }}>No users yet — add the first one.</div>
        ) : (
          data.items.map((u) => <UserRow key={u.id} u={u} allUsers={data.items} />)
        )}
      </div>
      <PrivacyPanel />
      {adding && <AddUserForm onClose={() => setAdding(false)} />}
    </>
  );
}
