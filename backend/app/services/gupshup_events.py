"""Pure parsing of Gupshup v2 callbacks (no DB). The facts, with doc URLs, are in
docs/superpowers/specs/2026-10-01-gupshup-contract.md (§3 events, §6 button taps)."""

# Template-, account- or wallet-level failures: every later recipient of the same campaign
# would fail the same way, so the campaign is paused instead of burning the list
# (contract Deltas 10, 11). Per-recipient codes (131026 undeliverable, 131047 window,
# 131049 per-user marketing limit, 131050 opted out, 1002 no WhatsApp) are NOT here.
CAMPAIGN_STOP_CODES = frozenset({132000, 132001, 132012, 132015, 132016, 4001, 4003, 4005,
                                 1003, 131042, 131031, 131048})

# wa_messages.status only ever moves forward; our own send writes 'submitted'.
WA_STATUS_RANK = {"submitted": 0, "enqueued": 1, "sent": 2, "delivered": 3, "read": 4, "failed": 5}


def event_ids(ev: dict) -> dict:
    """Which of our rows a message-event is about.
    key   — the send API's messageId: `gsId` when present (sent/delivered/read/async failed),
            else `id` (enqueued / sync failed; or a WhatsApp id when gsId is missing).
    wa_id — `payload.id`, matched against the WhatsApp id we stored (covers gsId-less events).
    learn — a WhatsApp id to remember: enqueued's payload.whatsappMessageId, or `id` when
            gsId is present (then `id` is the WhatsApp id)."""
    gs, i = ev.get("gsId"), ev.get("id")
    inner = ev.get("payload") or {}
    if ev.get("type") == "enqueued":
        learn = inner.get("whatsappMessageId")
    else:
        learn = i if gs else None
    return {"key": gs or i, "wa_id": i, "learn": learn}


def event_code(ev: dict) -> int | None:
    code = (ev.get("payload") or {}).get("code")
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


def event_error(ev: dict) -> str | None:
    """'<code>: <reason>' for a failed event — match on the code, never on the reason text
    (Gupshup spells reasons inconsistently, contract §3.5/§8)."""
    if ev.get("type") != "failed":
        return None
    inner = ev.get("payload") or {}
    code, reason = inner.get("code"), inner.get("reason")
    return f"{code}: {reason}" if code is not None else reason


def inbound_kind(payload: dict) -> str:
    """msg_type for an inbound message. A template quick-reply tap has an inner
    {"type": "button"} under either outer type ("quick_reply" or "text") — store it as
    one value so SQL and UI see one kind (contract §6, Delta 7)."""
    inner = payload.get("payload") or {}
    if isinstance(inner, dict) and inner.get("type") == "button":
        return "quick_reply"
    return payload.get("type") or "text"
