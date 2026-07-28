/* One WhatsApp conversation: bubbles + composer. Shared by the WhatsApp page and the
   lead-detail card so the 24-hour window rule lives in exactly one place — WhatsApp
   only delivers free-form text within 24h of the customer's last message. */
import { useState } from "react";
import { WaMessage } from "../lib/api";
import { useSendWa, formatDateTime } from "../lib/queries";

export const WINDOW_MS = 24 * 60 * 60 * 1000;

export function Bubble({ m }: { m: WaMessage }) {
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

interface Props {
  phone: string;
  messages: WaMessage[];       // oldest first
  lastInboundAt: number | null;
  sendEnabled: boolean;
}

export default function WaThread({ phone, messages, lastInboundAt, sendEnabled }: Props) {
  const send = useSendWa();
  const [draft, setDraft] = useState("");

  const windowOpen = lastInboundAt != null && Date.now() - lastInboundAt < WINDOW_MS;
  const blocked = !sendEnabled
    ? "Sending isn’t configured yet — GUPSHUP_SOURCE_NUMBER and GUPSHUP_APP_NAME are missing."
    : !windowOpen
      ? "The 24-hour reply window has closed. Only an approved template message can reach them now."
      : null;

  const submit = () => {
    const text = draft.trim();
    if (!text || blocked || send.isPending) return;
    send.mutate({ phone, text }, { onSuccess: () => setDraft("") });
  };

  return (
    <>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "2px 6px 2px 2px" }}>
        {messages.map((m) => <Bubble key={m.id} m={m} />)}
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
  );
}
