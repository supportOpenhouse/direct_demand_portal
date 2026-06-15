/* Settings & Access — user management. Only people added here can sign in, and
   each maps to their leads via the sheet's "Assigned to" name. */
import { useState } from "react";
import { useUsers, useUserMutations } from "../lib/queries";
import { ManagedUser } from "../lib/api";
import { useToast } from "../components/Toast";
import { useAuth } from "../components/AuthContext";

const ROLES = [
  { v: "admin", label: "Admin", desc: "All leads · manage users & source data" },
  { v: "cm", label: "Closing Manager", desc: "All team leads" },
  { v: "rm", label: "Relationship Manager", desc: "Own assigned leads only" },
];
const roleLabel = (r: string) => ROLES.find((x) => x.v === r)?.label || r;
const initials = (n: string | null, e: string) =>
  (n || e).split(/[ @]/).map((x) => x[0]).slice(0, 2).join("").toUpperCase();

function AddUserForm({ onClose }: { onClose: () => void }) {
  const { create } = useUserMutations();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("rm");

  const submit = () => {
    if (!email.trim() || !name.trim()) {
      toast("Email and name are required", "gold", "⚠");
      return;
    }
    create.mutate(
      { email: email.trim(), name: name.trim(), role },
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
          <div className="field">
            <label>Role</label>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r.v} value={r.v}>{r.label}</option>)}
            </select>
          </div>
          <div className="note" style={{ marginTop: 0 }}>
            {ROLES.find((r) => r.v === role)?.desc}
            {name.trim() && <> · maps leads assigned to <b>{name.trim().split(" ")[0]}</b></>}
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

  const submit = () => {
    if (!name.trim()) {
      toast("Name is required", "gold", "⚠");
      return;
    }
    update.mutate(
      { id: u.id, patch: { name: name.trim(), role } },
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
          <div className="field"><label>Role</label>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r.v} value={r.v}>{r.label}</option>)}
            </select></div>
          <div className="note" style={{ marginTop: 0 }}>
            Mapped to <b>{u.matched_leads}</b> leads by matching <b>{name.trim().split(" ")[0] || u.maps_to}</b> in the sheet's “Assigned to”.
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

function UserRow({ u }: { u: ManagedUser }) {
  const { update, remove } = useUserMutations();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
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
        onClick={() => update.mutate({ id: u.id, patch: { active: !u.active } })} />
      <button className="btn ghost sm" onClick={() => setEditing(true)}>✎ Edit</button>
      <button className="btn ghost sm" onClick={() => {
        if (confirm(`Remove ${u.name || u.email}?`)) remove.mutate(u.id, { onSuccess: () => toast("User removed", "blue", "✓") });
      }}>Remove</button>
      {editing && <EditUserForm u={u} onClose={() => setEditing(false)} />}
    </div>
  );
}

export default function Settings() {
  const { enabled, user } = useAuth();
  const { data, isLoading } = useUsers();
  const [adding, setAdding] = useState(false);
  const isAdmin = !enabled || user?.role === "admin";

  if (!isAdmin) {
    return <div className="card"><div className="empty" style={{ padding: 40 }}>Only admins can manage users.</div></div>;
  }

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
            <p className="sec-sub" style={{ margin: 0 }}>Only these people can sign in. Each maps to their leads by the sheet's “Assigned to” name.</p>
          </div>
          <button className="btn green" onClick={() => setAdding(true)}>+ Add user</button>
        </div>
        {isLoading ? (
          <div className="empty" style={{ padding: 30 }}>Loading users…</div>
        ) : !data?.items.length ? (
          <div className="empty" style={{ padding: 30 }}>No users yet — add the first one.</div>
        ) : (
          data.items.map((u) => <UserRow key={u.id} u={u} />)
        )}
      </div>
      {adding && <AddUserForm onClose={() => setAdding(false)} />}
    </>
  );
}
