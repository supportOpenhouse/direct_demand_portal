/* WhatsApp — inbound feed from the Gupshup webhook.
   Phase 1: the server keeps the last 50 raw callbacks in memory, so this reads them
   straight through with no schema in between. Replies and threading come once the
   payloads are modelled into a table. */
import { useState } from "react";
import { useGupshupRecent, formatDateTime } from "../lib/queries";
import { GupshupEvent } from "../lib/api";
import { WhatsAppIcon } from "../components/icons";
import { initials } from "../lib/leads";

/* Gupshup nests the message body one level deeper than the envelope:
   { type: "message", payload: { source, type, payload: {...}, sender: {...} } } */
function preview(e: GupshupEvent): string {
  const p = e.body?.payload ?? {};
  const inner = p.payload ?? {};
  if (p.type === "text") return inner.text ?? "";
  if (p.type === "location") return `📍 ${inner.name ?? "Location"}`;
  if (p.type) return `${inner.caption || ""} [${p.type}]`.trim();
  return "";
}

function sender(e: GupshupEvent): { name: string; phone: string } {
  const p = e.body?.payload ?? {};
  return { name: p.sender?.name || "Unknown", phone: p.sender?.phone || p.source || "" };
}

const EVENT_COLOR: Record<string, string> = {
  delivered: "var(--emerald)", read: "var(--blue)", sent: "var(--slate)",
  failed: "var(--coral)", enqueued: "var(--muted)",
};

export default function Chat() {
  const { data, isLoading, error, isFetching } = useGupshupRecent();
  const [showRaw, setShowRaw] = useState(false);

  const items = data?.items ?? [];
  const messages = items.filter((e) => e.type === "message");
  const events = items.filter((e) => e.type !== "message");

  if (isLoading) return <div className="card"><div className="empty" style={{ padding: 48 }}>Loading…</div></div>;

  if (error) {
    return (
      <div className="card">
        <div className="empty" style={{ padding: 48 }}>
          <div style={{ fontWeight: 600, color: "var(--coral)" }}>Couldn’t reach the webhook feed</div>
          <div style={{ fontSize: 12.5, marginTop: 4 }}>{(error as Error).message}</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{messages.length}</b> inbound message{messages.length === 1 ? "" : "s"}
          {events.length ? ` · ${events.length} event${events.length === 1 ? "" : "s"}` : ""}
          {isFetching ? " · updating…" : ""}
        </p>
        <button className="btn ghost sm" onClick={() => setShowRaw((v) => !v)}>
          {showRaw ? "Hide" : "Show"} raw callbacks
        </button>
      </div>

      {messages.length === 0 ? (
        <div className="card">
          <div className="empty" style={{ padding: 48, textAlign: "center" }}>
            <div style={{ width: 40, height: 40, margin: "0 auto 10px", color: "#25b15a" }}><WhatsAppIcon /></div>
            <div style={{ fontWeight: 600, color: "var(--ink-2)" }}>No messages yet</div>
            <div style={{ fontSize: 12.5, marginTop: 6, lineHeight: 1.6 }}>
              Set the callback URL in the Gupshup dashboard (Overview → Webhooks), then send a
              WhatsApp message to your business number. It shows up here within 10 seconds.
            </div>
          </div>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {messages.map((e, i) => {
            const { name, phone } = sender(e);
            return (
              <div
                key={i}
                style={{
                  display: "flex", gap: 12, padding: "13px 16px", alignItems: "flex-start",
                  borderTop: i ? "1px solid var(--line)" : undefined,
                }}
              >
                <div className="av" style={{ background: "#daf3e3", color: "#12823f", flexShrink: 0 }}>
                  {initials(name)}
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                    <b style={{ fontSize: 13.5 }}>{name}</b>
                    <span style={{ fontSize: 11.5, color: "var(--muted)", fontVariantNumeric: "tabular-nums" }}>
                      {phone}
                    </span>
                    <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap" }}>
                      {formatDateTime(e.received_at)}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: "var(--ink-2)", marginTop: 3, wordBreak: "break-word" }}>
                    {preview(e) || <i style={{ color: "var(--muted)" }}>(no text)</i>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showRaw && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="sec-sub" style={{ marginBottom: 8 }}>
            Every callback as received — delivery receipts, opt-ins, billing. This is the
            reference for modelling the payloads.
          </div>
          {items.length === 0 ? (
            <div className="empty" style={{ padding: 24 }}>Nothing received yet.</div>
          ) : (
            items.map((e, i) => (
              <details key={i} style={{ borderTop: i ? "1px solid var(--line)" : undefined, padding: "8px 0" }}>
                <summary style={{ cursor: "pointer", fontSize: 12.5 }}>
                  <span style={{ color: EVENT_COLOR[e.body?.payload?.type] ?? "var(--ink-2)", fontWeight: 600 }}>
                    {e.type ?? "unknown"}
                  </span>
                  <span style={{ color: "var(--muted)", marginLeft: 8 }}>{formatDateTime(e.received_at)}</span>
                </summary>
                <pre style={{ fontSize: 11.5, overflowX: "auto", marginTop: 6, color: "var(--ink-2)" }}>
                  {JSON.stringify(e.body, null, 2)}
                </pre>
              </details>
            ))
          )}
        </div>
      )}
    </>
  );
}
