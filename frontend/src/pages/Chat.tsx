/* WhatsApp — two-way chat over the Gupshup webhook + send API.

   WhatsApp only allows free-form replies within 24h of the customer's last message;
   outside that window only pre-approved templates go through. The composer reflects
   that state rather than letting you type into a message that will be rejected.

   RMs see only the conversations assigned to them; admins see everything and can
   reassign. Scoping is enforced server-side — this page just reflects it. */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { markWaSeen } from "../lib/whatsapp";
import { CITIES } from "../lib/leads";
import {
  useWaMessages, useCreateWaLead, useMarkWaContact, useAssignWaContact, useAssignees,
  useBackfillWaAssign, useSocietiesByCity, useGupshupRecent, useBulkCreateWaLeads,
  formatDateTime,
} from "../lib/queries";
import WaThread from "../components/WaThread";
import { WaMessage, WaTag, WA_TAGS } from "../lib/api";
import { useAuth } from "../components/AuthContext";
import { useToast } from "../components/Toast";
import { WhatsAppIcon } from "../components/icons";

const WINDOW_MS = 24 * 60 * 60 * 1000;
// fixed panel height — both columns scroll inside this rather than running to the
// bottom of the viewport, so the page keeps a normal, predictable shape
const PANEL_H = 560;

interface Thread {
  phone: string;
  name: string | null;
  messages: WaMessage[];   // oldest first, for rendering
  lastAt: number;
  lastInboundAt: number | null;
}

/* One flat list from the server → per-phone threads, most recently active first. */
/* Red for rejected, blue for everything else — matching the row background. */
function TagChip({ tag }: { tag: WaTag }) {
  const rejected = tag === "rejected";
  return (
    <span
      className="bucket-tag"
      style={{
        marginLeft: 6,
        background: rejected ? "var(--coral-soft)" : "var(--blue-soft)",
        color: rejected ? "var(--coral)" : "var(--blue)",
      }}
    >
      {tag}
    </span>
  );
}

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

export default function Chat() {
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";

  const { data, isLoading, error } = useWaMessages();
  const toast = useToast();
  const [active, setActive] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [creating, setCreating] = useState(false);
  const [marking, setMarking] = useState(false);
  // bulk lead creation: off until the button is pressed, so the list stays a plain
  // conversation list the rest of the time
  const [bulk, setBulk] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  // keep marking seen while the page is open, so the dot doesn't reappear behind you
  useEffect(() => { if (data) markWaSeen(); }, [data]);

  const threads = useMemo(() => toThreads(data?.items ?? []), [data]);
  const thread = threads.find((t) => t.phone === active) ?? threads[0] ?? null;
  // leads are keyed by the last 10 digits — leads store "+91 98715 78484", WhatsApp "919871578484"
  const lead = thread ? data?.leads?.[thread.phone.slice(-10)] : undefined;
  const tag = thread ? data?.tags?.[thread.phone.slice(-10)] : undefined;
  const owner = thread ? data?.owners?.[thread.phone.slice(-10)] : undefined;

  /* Only conversations without a lead can be converted — the endpoint skips the rest
     anyway, but offering a checkbox that does nothing is worse than not offering it. */
  const convertible = useMemo(
    () => threads.filter((t) => !data?.leads?.[t.phone.slice(-10)]).map((t) => t.phone),
    [threads, data],
  );
  const bulkCreate = useBulkCreateWaLeads();
  const toggleOne = (phone: string) => setPicked((prev) => {
    const next = new Set(prev);
    next.has(phone) ? next.delete(phone) : next.add(phone);
    return next;
  });
  const exitBulk = () => { setBulk(false); setPicked(new Set()); };
  const runBulk = () => bulkCreate.mutate([...picked], {
    onSuccess: (r) => {
      const skipped = r.skipped_existing ? ` · ${r.skipped_existing} already had one` : "";
      // they land unassigned by design — say so, or nobody goes looking for them
      toast(`Created ${r.created} unassigned lead${r.created === 1 ? "" : "s"}${skipped}`,
            r.created ? "green" : "gold", r.created ? "✓" : "⚠");
      exitBulk();
    },
    onError: (e: any) => toast(e.message, "gold", "⚠"),
  });

  const sendEnabled = data?.send_enabled ?? false;

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

  return (
    <div>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{threads.length}</b> conversation{threads.length === 1 ? "" : "s"}
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {bulk ? (
            <>
              <span style={{ fontSize: 12, color: "var(--muted)" }}>
                {picked.size} of {convertible.length} selected
              </span>
              <button className="btn ghost sm"
                onClick={() => setPicked(picked.size === convertible.length
                  ? new Set() : new Set(convertible))}>
                {picked.size === convertible.length && convertible.length > 0 ? "Clear all" : "Select all"}
              </button>
              <button className="btn primary sm" disabled={!picked.size || bulkCreate.isPending}
                onClick={runBulk}>
                {bulkCreate.isPending ? "Creating…" : `Create ${picked.size} lead${picked.size === 1 ? "" : "s"}`}
              </button>
              <button className="btn ghost sm" onClick={exitBulk}>Cancel</button>
            </>
          ) : (
            <>
              <button className="btn sm" onClick={() => setBulk(true)} disabled={!convertible.length}
                title={convertible.length
                  ? "Turn conversations into leads in bulk"
                  : "Every conversation already has a lead"}>
                Create leads ({convertible.length})
              </button>
              {isAdmin && <BackfillButton />}
              <button className="btn ghost sm" onClick={() => setShowRaw((v) => !v)}>
                {showRaw ? "Hide" : "Show"} raw callbacks
              </button>
            </>
          )}
        </div>
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
          // fixed, not flex:1 — the two panels scroll independently rather than
          // stretching to the bottom of the viewport
          height: PANEL_H,
        }}>
          {/* thread list */}
          <div className="card" style={{ padding: 0, overflowY: "auto" }}>
            {threads.map((t, i) => {
              const last = t.messages[t.messages.length - 1];
              const selected = t.phone === thread?.phone;
              const hasLead = !!data?.leads?.[t.phone.slice(-10)];
              const rowTag = data?.tags?.[t.phone.slice(-10)];
              const rowOwner = data?.owners?.[t.phone.slice(-10)];
              return (
                <div key={t.phone} style={{
                  display: "flex", alignItems: "center",
                  borderTop: i ? "1px solid var(--line)" : undefined,
                }}>
                  {/* Checkbox sits OUTSIDE the row button — nesting a control inside a
                      button is invalid, and clicking the box would also open the chat.
                      Rows that already have a lead get a spacer, so nothing shifts. */}
                  {bulk && (hasLead
                    ? <span style={{ width: 30, flex: "none", textAlign: "center",
                                     fontSize: 10, color: "var(--muted)" }} title="Already a lead">✓</span>
                    : <input
                        type="checkbox"
                        checked={picked.has(t.phone)}
                        onChange={() => toggleOne(t.phone)}
                        aria-label={`Select ${t.name || t.phone}`}
                        style={{ width: 30, flex: "none", accentColor: "var(--emerald)", cursor: "pointer" }}
                      />)}
                <button
                  onClick={() => setActive(t.phone)}
                  style={{
                    display: "flex", gap: 10, width: "100%", textAlign: "left", padding: "11px 13px",
                    border: 0, cursor: "pointer",
                    font: "inherit", alignItems: "center",
                    // Two independent signals, so they use two channels:
                    //   background = the mark (red rejected, blue everything else)
                    //   left bar    = a lead exists (amber), which must stay visible
                    // With no mark, the background falls back to amber so lead-created
                    // still reads on its own.
                    background: selected ? "var(--panel-2)"
                      : rowTag === "rejected" ? "var(--coral-soft)"
                      : rowTag ? "var(--blue-soft)"
                      : hasLead ? "var(--amber-soft)" : "transparent",
                    borderLeft: hasLead ? "3px solid var(--amber)" : "3px solid transparent",
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {t.name || t.phone}
                      {rowTag && <TagChip tag={rowTag} />}
                      {isAdmin && rowOwner && (
                        <span style={{ marginLeft: 6, fontSize: 10.5, fontWeight: 500, color: "var(--muted)" }}>
                          {rowOwner.split(" ")[0]}
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {last?.direction === "out" ? "You: " : ""}{last?.body || `[${last?.msg_type}]`}
                    </div>
                  </div>
                </button>
                </div>
              );
            })}
          </div>

          {/* conversation */}
          {/* .card carries no padding of its own — every page adds its own inset */}
          <div className="card" style={{ display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden", padding: 14 }}>
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
                  {/* sits with the number it describes, not with the lead actions */}
                  <button className="btn ghost sm" style={{ marginLeft: 10 }} onClick={() => setMarking(true)}>
                    {tag ? `Marked: ${tag}` : "Mark read"}
                  </button>
                  {isAdmin ? (
                    <OwnerPicker phone={thread.phone} owner={owner} />
                  ) : owner ? (
                    <span style={{ marginLeft: 10, fontSize: 11.5, color: "var(--muted)" }}>· {owner}</span>
                  ) : null}
                  <div style={{ marginLeft: "auto" }}>
                    {lead ? (
                      <Link to={`/leads/${lead.id}`} className="btn ghost sm">View lead</Link>
                    ) : (
                      <button className="btn green sm" onClick={() => setCreating(true)}>+ Create new lead</button>
                    )}
                  </div>
                </div>

                <WaThread
                  phone={thread.phone}
                  messages={thread.messages}
                  lastInboundAt={thread.lastInboundAt}
                  sendEnabled={sendEnabled}
                />
              </>
            )}
          </div>
        </div>
      )}

      {showRaw && <RawFeed />}

      {marking && thread && (
        <MarkModal phone={thread.phone} current={tag} onClose={() => setMarking(false)} />
      )}

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

/* One-shot distribution of conversations that predate assignment. */
function BackfillButton() {
  const fill = useBackfillWaAssign();
  return (
    <button className="btn ghost sm" disabled={fill.isPending}
      title="Give every unassigned conversation an owner"
      onClick={() => fill.mutate()}>
      {fill.isPending ? "Assigning…"
        : fill.data ? `Assigned ${fill.data.assigned}` : "Assign unowned"}
    </button>
  );
}

/* Reassign a conversation. Admin-only — an RM moving their own threads away would
   defeat the point of distributing them, so the API refuses it too. */
function OwnerPicker({ phone, owner }: { phone: string; owner?: string }) {
  const { data } = useAssignees();
  const assign = useAssignWaContact();
  return (
    <select
      value={owner ?? ""}
      disabled={assign.isPending}
      onChange={(e) => assign.mutate({ phone, assigned_to: e.target.value || null })}
      title="Who owns this conversation"
      style={{
        marginLeft: 8, fontSize: 11.5, padding: "4px 8px", borderRadius: 8,
        border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink-2)",
        maxWidth: 150,
      }}
    >
      <option value="">Unassigned</option>
      {(data?.items ?? []).map((a) => <option key={a.email} value={a.name}>{a.name}</option>)}
    </select>
  );
}

/* Mark what this number turned out to be. Re-marking overwrites, so the current mark
   is preselected rather than hidden. */
function MarkModal(
  { phone, current, onClose }: { phone: string; current?: WaTag; onClose: () => void },
) {
  const mark = useMarkWaContact();
  const [tag, setTag] = useState<WaTag>(current ?? "buyer");

  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ width: "min(420px, 100%)" }}>
        <div className="mh">
          <h3>Mark this contact</h3>
          <div className="icon-btn" onClick={onClose}>✕</div>
        </div>
        <div className="mb">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {WA_TAGS.map((t) => (
              <label
                key={t}
                style={{
                  display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
                  borderRadius: 9, cursor: "pointer", fontSize: 13.5, textTransform: "capitalize",
                  border: "1px solid " + (tag === t ? "var(--emerald)" : "var(--line)"),
                  background: tag === t ? "var(--emerald-soft)" : "var(--panel)",
                }}
              >
                <input type="radio" name="wa-tag" checked={tag === t} onChange={() => setTag(t)}
                  style={{ accentColor: "var(--emerald)" }} />
                {t}
                {t === "rejected" && (
                  <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--coral)" }}>
                    highlights red
                  </span>
                )}
              </label>
            ))}
          </div>
          {mark.isError && (
            <div style={{ marginTop: 10, fontSize: 12, color: "var(--coral)" }}>
              {(mark.error as Error).message}
            </div>
          )}
        </div>
        <div className="mf">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn green"
            disabled={mark.isPending}
            onClick={() => mark.mutate({ phone, tag }, { onSuccess: onClose })}
          >
            {mark.isPending ? "Saving…" : "Mark"}
          </button>
        </div>
      </div>
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
