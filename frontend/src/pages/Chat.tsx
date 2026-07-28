/* WhatsApp — two-way chat over the Gupshup webhook + send API.

   WhatsApp only allows free-form replies within 24h of the customer's last message;
   outside that window only pre-approved templates go through. The composer reflects
   that state rather than letting you type into a message that will be rejected.

   Admin-only for now — the API refuses non-admins too, this just avoids showing a
   dead page. */
import { useMemo, useState } from "react";
import { useWaMessages, useSendWa, useGupshupRecent, formatDateTime } from "../lib/queries";
import { WaMessage } from "../lib/api";
import { useAuth } from "../components/AuthContext";
import { WhatsAppIcon } from "../components/icons";
import { initials } from "../lib/leads";

const WINDOW_MS = 24 * 60 * 60 * 1000;

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

  const threads = useMemo(() => toThreads(data?.items ?? []), [data]);
  const thread = threads.find((t) => t.phone === active) ?? threads[0] ?? null;

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
    <>
      <div className="section-head" style={{ marginBottom: 10 }}>
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
        <div style={{ display: "grid", gridTemplateColumns: "minmax(200px, 280px) 1fr", gap: 12 }}>
          {/* thread list */}
          <div className="card" style={{ padding: 0, overflow: "hidden", alignSelf: "start" }}>
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
                  <div className="av" style={{ background: "#daf3e3", color: "#12823f", flexShrink: 0 }}>
                    {initials(t.name || t.phone)}
                  </div>
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
          <div className="card" style={{ display: "flex", flexDirection: "column", minHeight: 420 }}>
            {thread && (
              <>
                <div style={{ borderBottom: "1px solid var(--line)", paddingBottom: 9, marginBottom: 11 }}>
                  <b style={{ fontSize: 14 }}>{thread.name || thread.phone}</b>
                  <span style={{ fontSize: 11.5, color: "var(--muted)", marginLeft: 8, fontVariantNumeric: "tabular-nums" }}>
                    +{thread.phone}
                  </span>
                </div>

                <div style={{ flex: 1, overflowY: "auto", maxHeight: 460, paddingRight: 4 }}>
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
    </>
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
