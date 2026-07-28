/* WhatsApp — two-way chat over the Gupshup webhook + send API.

   WhatsApp only allows free-form replies within 24h of the customer's last message;
   outside that window only pre-approved templates go through. The composer reflects
   that state rather than letting you type into a message that will be rejected.

   Admin-only for now — the API refuses non-admins too, this just avoids showing a
   dead page. */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  useWaMessages, useSendWa, useCreateWaLead, useSocietiesByCity, useGupshupRecent, formatDateTime,
} from "../lib/queries";
import { WaMessage } from "../lib/api";
import { useAuth } from "../components/AuthContext";
import { WhatsAppIcon } from "../components/icons";

const WINDOW_MS = 24 * 60 * 60 * 1000;
const CITIES = ["Ghaziabad", "Noida", "Gurgaon"];

interface Thread {
  phone: string;
  name: string | null;
  messages: WaMessage[];   // oldest first, for rendering
  lastAt: number;
  lastInboundAt: number | null;
}

/* One flat list from the server → per-phone threads, most recently active first. */
function toThreads(items: WaMessage[]): Thread[] {
  const by = new Map<string, Thread>();
  for (const m of items) {
    const t = by.get(m.phone) ?? { phone: m.phone, name: null, messages: [], lastAt: 0, lastInboundAt: null };
    t.messages.push(m);
    if (m.direction === "in") {
      t.name = t.name ?? m.name;
      t.lastInboundAt = Math.max(t.lastInboundAt ?? 0, +new Date(m.created_at));
    }
    t.lastAt = Math.max(t.lastAt, +new Date(m.created_at));
    by.set(m.phone, t);
  }
  const threads = [...by.values()];
  threads.forEach((t) => t.messages.reverse()); // server sends newest first
  return threads.sort((a, b) => b.lastAt - a.lastAt);
}

function Bubble({ m }: { m: WaMessage }) {
  const out = m.direction === "out";
  return (
    <div style={{ display: "flex", justifyContent: out ? "flex-end" : "flex-start", marginBottom: 8 }}>
      <div
        style={{
          maxWidth: "72%", padding: "8px 11px", borderRadius: 12, fontSize: 13, lineHeight: 1.45,
          background: out ? "#d6f5e0" : "var(--panel-2)", color: "var(--ink)",
          borderBottomRightRadius: out ? 3 : 12, borderBottomLeftRadius: out ? 12 : 3,
          wordBreak: "break-word",
        }}
      >
        {m.body || <i style={{ color: "var(--muted)" }}>[{m.msg_type}]</i>}
        <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 3, textAlign: "right" }}>
          {formatDateTime(m.created_at)}
          {out && m.status ? ` · ${m.status}` : ""}
        </div>
      </div>
    </div>
  );
}

export default function Chat() {
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";

  const { data, isLoading, error } = useWaMessages();
  const send = useSendWa();
  const [active, setActive] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [showRaw, setShowRaw] = useState(false);
  const [creating, setCreating] = useState(false);

  const threads = useMemo(() => toThreads(data?.items ?? []), [data]);
  const thread = threads.find((t) => t.phone === active) ?? threads[0] ?? null;
  // leads are keyed by the last 10 digits — leads store "+91 98715 78484", WhatsApp "919871578484"
  const lead = thread ? data?.leads?.[thread.phone.slice(-10)] : undefined;

  // WhatsApp's rule, not ours: the clock runs from THEIR last message.
  const windowOpen = thread?.lastInboundAt != null && Date.now() - thread.lastInboundAt < WINDOW_MS;
  const sendEnabled = data?.send_enabled ?? false;
  const blocked = !sendEnabled
    ? "Sending isn’t configured yet — GUPSHUP_SOURCE_NUMBER and GUPSHUP_APP_NAME are missing."
    : !windowOpen
      ? "The 24-hour reply window has closed. Only an approved template message can reach them now."
      : null;

  if (!isAdmin) {
    return (
      <div className="card">
        <div className="empty" style={{ padding: 48 }}>WhatsApp is admin-only for now.</div>
      </div>
    );
  }
  if (isLoading) return <div className="card"><div className="empty" style={{ padding: 48 }}>Loading…</div></div>;
  if (error) {
    return (
      <div className="card">
        <div className="empty" style={{ padding: 48 }}>
          <div style={{ fontWeight: 600, color: "var(--coral)" }}>Couldn’t load messages</div>
          <div style={{ fontSize: 12.5, marginTop: 4 }}>{(error as Error).message}</div>
        </div>
      </div>
    );
  }

  const submit = () => {
    const text = draft.trim();
    if (!text || !thread || blocked || send.isPending) return;
    send.mutate({ phone: thread.phone, text }, { onSuccess: () => setDraft("") });
  };

  return (
    // fills .view (a bounded flex child of .main) so the thread list and conversation
    // scroll inside themselves rather than growing the page
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100%" }}>
      <div className="section-head" style={{ marginBottom: 10, flex: "none" }}>
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{threads.length}</b> conversation{threads.length === 1 ? "" : "s"}
        </p>
        <button className="btn ghost sm" onClick={() => setShowRaw((v) => !v)}>
          {showRaw ? "Hide" : "Show"} raw callbacks
        </button>
      </div>

      {threads.length === 0 ? (
        <div className="card">
          <div className="empty" style={{ padding: 48, textAlign: "center" }}>
            <div style={{ width: 40, height: 40, margin: "0 auto 10px", color: "#25b15a" }}><WhatsAppIcon /></div>
            <div style={{ fontWeight: 600, color: "var(--ink-2)" }}>No conversations yet</div>
            <div style={{ fontSize: 12.5, marginTop: 6, lineHeight: 1.6 }}>
              A customer has to message your business number first — WhatsApp doesn’t let a
              business open a conversation with free-form text.
            </div>
          </div>
        </div>
      ) : (
        <div style={{
          display: "grid", gridTemplateColumns: "minmax(200px, 280px) 1fr", gap: 12,
          flex: 1, minHeight: 0,  // minHeight:0 or the grid refuses to shrink below content
        }}>
          {/* thread list */}
          <div className="card" style={{ padding: 0, overflowY: "auto" }}>
            {threads.map((t, i) => {
              const last = t.messages[t.messages.length - 1];
              return (
                <button
                  key={t.phone}
                  onClick={() => setActive(t.phone)}
                  style={{
                    display: "flex", gap: 10, width: "100%", textAlign: "left", padding: "11px 13px",
                    border: 0, borderTop: i ? "1px solid var(--line)" : undefined, cursor: "pointer",
                    font: "inherit", alignItems: "center",
                    background: t.phone === thread?.phone ? "var(--panel-2)" : "transparent",
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {t.name || t.phone}
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {last?.direction === "out" ? "You: " : ""}{last?.body || `[${last?.msg_type}]`}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* conversation */}
          {/* .card carries no padding of its own — every page adds its own inset */}
          <div className="card" style={{ display: "flex", flexDirection: "column", minHeight: 0, padding: 14 }}>
            {thread && (
              <>
                <div style={{
                  borderBottom: "1px solid var(--line)", paddingBottom: 9, marginBottom: 11,
                  display: "flex", alignItems: "center",
                }}>
                  <b style={{ fontSize: 14 }}>{thread.name || thread.phone}</b>
                  <span style={{ fontSize: 11.5, color: "var(--muted)", marginLeft: 16, fontVariantNumeric: "tabular-nums" }}>
                    +{thread.phone}
                  </span>
                  <div style={{ marginLeft: "auto" }}>
                    {lead ? (
                      <Link to={`/leads/${lead.id}`} className="btn ghost sm">View lead</Link>
                    ) : (
                      <button className="btn green sm" onClick={() => setCreating(true)}>+ Create new lead</button>
                    )}
                  </div>
                </div>

                <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "2px 6px 2px 2px" }}>
                  {thread.messages.map((m) => <Bubble key={m.id} m={m} />)}
                </div>

                {blocked ? (
                  <div style={{
                    marginTop: 10, padding: "10px 12px", borderRadius: 9, fontSize: 12.5,
                    background: "var(--panel-2)", color: "var(--ink-2)", lineHeight: 1.5,
                  }}>
                    {blocked}
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "flex-end" }}>
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
                      }}
                      placeholder="Message… (Enter to send, Shift+Enter for a new line)"
                      rows={2}
                      style={{
                        flex: 1, resize: "none", font: "inherit", fontSize: 13, padding: "9px 11px",
                        borderRadius: 9, border: "1px solid var(--line)", background: "var(--panel)",
                        color: "var(--ink)",
                      }}
                    />
                    <button className="btn wa" onClick={submit} disabled={send.isPending || !draft.trim()}>
                      {send.isPending ? "Sending…" : "Send"}
                    </button>
                  </div>
                )}
                {send.isError && (
                  <div style={{ marginTop: 7, fontSize: 12, color: "var(--coral)" }}>
                    {(send.error as Error).message}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {showRaw && <RawFeed />}

      {creating && thread && (
        <CreateLeadModal
          phone={thread.phone}
          name={thread.name || ""}
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

/* Name and number come from the conversation; city and society are optional because
   a WhatsApp lead usually hasn't told us either yet. Source is fixed server-side. */
function CreateLeadModal(
  { phone, name, onClose }: { phone: string; name: string; onClose: () => void },
) {
  const create = useCreateWaLead();
  const [form, setForm] = useState({ name, city: "", society: "" });
  const societies = useSocietiesByCity(form.city);
  const societyOptions = societies.data?.items ?? [];
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = () => {
    if (!form.name.trim() || create.isPending) return;
    create.mutate(
      { phone, name: form.name.trim(), city: form.city.trim(), society: form.society.trim() },
      { onSuccess: onClose },
    );
  };

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="mh">
          <h3>Create lead from WhatsApp</h3>
          <div className="icon-btn" onClick={onClose}>✕</div>
        </div>
        <div className="mb">
          <div className="field">
            <label>Name <span className="req">*</span></label>
            <input value={form.name} autoFocus onChange={set("name")} placeholder="Full name" />
          </div>
          <div className="field">
            <label>Phone</label>
            {/* the conversation's number — editing it would detach the lead from the thread */}
            <input value={`+${phone}`} readOnly style={{ background: "var(--panel-2)", color: "var(--muted)" }} />
          </div>
          <div className="field">
            <label>City</label>
            <select
              value={form.city}
              // changing city invalidates the chosen society — it may not exist there
              onChange={(e) => setForm((f) => ({ ...f, city: e.target.value, society: "" }))}
            >
              <option value="">Choose city (optional)</option>
              {CITIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Society</label>
            <select
              value={form.society}
              disabled={!form.city}
              onChange={(e) => setForm((f) => ({ ...f, society: e.target.value }))}
            >
              <option value="">
                {!form.city ? "Enter city first"
                  : societies.isLoading ? "Loading…"
                  : societyOptions.length ? "Choose society (optional)"
                  : "No societies found for this city"}
              </option>
              {societyOptions.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          {create.isError && (
            <div style={{ marginTop: 10, fontSize: 12, color: "var(--coral)" }}>
              {(create.error as Error).message}
            </div>
          )}
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn green" onClick={submit} disabled={create.isPending || !form.name.trim()}>
            {create.isPending ? "Creating…" : "Create lead"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* Every callback as received — delivery receipts, opt-ins, billing. The reference
   for anything wa_messages doesn't model yet. Its own component so the query only
   runs while the panel is open. */
function RawFeed() {
  const { data } = useGupshupRecent();
  const items = data?.items ?? [];
  return (
    <div className="card" style={{ marginTop: 12 }}>
      {items.length === 0 ? (
        <div className="empty" style={{ padding: 24 }}>Nothing received yet.</div>
      ) : (
        items.map((e, i) => (
          <details key={i} style={{ borderTop: i ? "1px solid var(--line)" : undefined, padding: "8px 0" }}>
            <summary style={{ cursor: "pointer", fontSize: 12.5 }}>
              <b>{e.type ?? "unknown"}</b>
              <span style={{ color: "var(--muted)", marginLeft: 8 }}>{formatDateTime(e.received_at)}</span>
            </summary>
            <pre style={{ fontSize: 11.5, overflowX: "auto", marginTop: 6, color: "var(--ink-2)" }}>
              {JSON.stringify(e.body, null, 2)}
            </pre>
          </details>
        ))
      )}
    </div>
  );
}
