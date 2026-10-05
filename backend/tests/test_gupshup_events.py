"""Gupshup callback parsing — the contract: docs/superpowers/specs/2026-10-01-gupshup-contract.md"""
from app.services.gupshup_events import CAMPAIGN_STOP_CODES, event_code, event_error, event_ids, inbound_kind


def test_enqueued_carries_our_id_and_teaches_the_whatsapp_id():
    ev = {"id": "g1", "type": "enqueued", "destination": "919876543210",
          "payload": {"whatsappMessageId": "w1", "type": "session"}}
    assert event_ids(ev) == {"key": "g1", "wa_id": "g1", "learn": "w1"}


def test_later_events_carry_our_id_in_gsid():
    # contract §3: for sent/delivered/read, id = the WhatsApp id, gsId = the send API's messageId
    ev = {"id": "w1", "gsId": "g1", "type": "delivered", "destination": "919876543210", "payload": {"ts": 1}}
    assert event_ids(ev) == {"key": "g1", "wa_id": "w1", "learn": "w1"}


def test_without_gsid_the_whatsapp_id_still_matches():
    # >1 week after the send, or an MM Lite DLR: no gsId, payload.id is the WhatsApp id
    ev = {"id": "w1", "type": "read", "destination": "919876543210", "payload": {"ts": 1}}
    assert event_ids(ev) == {"key": "w1", "wa_id": "w1", "learn": None}


def test_failed_keeps_the_code_and_reason():
    ev = {"id": "w1", "gsId": "g1", "type": "failed",
          "payload": {"code": 131026, "reason": "Message undeliverable"}}
    assert event_code(ev) == 131026
    assert event_error(ev) == "131026: Message undeliverable"
    assert event_error({"id": "g1", "type": "failed", "payload": {"reason": "x"}}) == "x"
    assert event_error({"id": "g1", "type": "delivered", "payload": {}}) is None


def test_campaign_level_codes_stop_the_campaign_per_recipient_ones_do_not():
    for c in (132000, 132001, 132012, 132015, 132016, 4001, 4003, 4005, 1003, 131042, 131031, 131048):
        assert c in CAMPAIGN_STOP_CODES, c
    for c in (131026, 131047, 131049, 131050, 1002):
        assert c not in CAMPAIGN_STOP_CODES, c


def test_a_template_button_tap_is_a_quick_reply_whichever_outer_type_gupshup_uses():
    inner = {"text": "Yes", "type": "button", "postbackText": "x"}
    assert inbound_kind({"type": "quick_reply", "payload": inner}) == "quick_reply"
    assert inbound_kind({"type": "text", "payload": inner}) == "quick_reply"
    assert inbound_kind({"type": "text", "payload": {"text": "hi"}}) == "text"
    assert inbound_kind({"type": "image", "payload": {"url": "u"}}) == "image"
