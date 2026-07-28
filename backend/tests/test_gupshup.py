from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.gupshup import _RECENT, parse_body, router

# bare app — the real one's lifespan wants a DB; the router is what's under test
app = FastAPI()
app.include_router(router, prefix="/v1")
client = TestClient(app)

# real Gupshup WhatsApp callback shapes
INBOUND = {
    "app": "DirectDemand", "timestamp": 1580227766370, "version": 2, "type": "message",
    "payload": {
        "id": "ABEGkYaYVSEEAhAL3SLAWwHKeKrt6s3FKB0c", "source": "918x8x8x8x8x", "type": "text",
        "payload": {"text": "Hi, is the 2BHK still available?"},
        "sender": {"phone": "918x8x8x8x8x", "name": "Ravi", "country_code": "91", "dial_code": "8x8x8x8x8x"},
    },
}
EVENT = {
    "app": "DirectDemand", "timestamp": 1580227766370, "version": 2, "type": "message-event",
    "payload": {"id": "d8e5c8f0", "type": "delivered", "destination": "918x8x8x8x8x"},
}


def test_parse_body_json_form_and_garbage():
    assert parse_body(b'{"type":"message"}', "application/json") == {"type": "message"}
    assert parse_body(b"a=1&b=2", "application/x-www-form-urlencoded") == {"a": "1", "b": "2"}
    assert parse_body(b"", "application/json") == {}
    assert parse_body(b"not json", "application/json") == "not json"  # kept, not dropped


def test_webhook_records_both_callback_types():
    _RECENT.clear()
    assert client.get("/v1/gupshup/webhook").json() == {"status": "ok"}
    for payload in (INBOUND, EVENT):
        r = client.post("/v1/gupshup/webhook", json=payload)
        assert r.status_code == 200
        assert r.content == b""  # Gupshup wants an empty 2xx body

    items = list(_RECENT)
    assert [i["type"] for i in items] == ["message-event", "message"]  # newest first
    assert items[1]["body"]["payload"]["payload"]["text"] == "Hi, is the 2BHK still available?"


def test_malformed_body_still_returns_200():
    """A 500 here would make Gupshup retry, then disable the callback URL."""
    _RECENT.clear()
    r = client.post(
        "/v1/gupshup/webhook", content=b"<xml>surprise</xml>", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 200
    assert list(_RECENT)[0]["body"] == "<xml>surprise</xml>"


def test_token_enforced_when_configured(monkeypatch):
    from app import config

    monkeypatch.setattr(config.get_settings(), "GUPSHUP_WEBHOOK_SECRET", "s3cret")
    assert client.post("/v1/gupshup/webhook", json=INBOUND).status_code == 403
    assert client.post("/v1/gupshup/webhook?token=wrong", json=INBOUND).status_code == 403
    assert client.post("/v1/gupshup/webhook?token=s3cret", json=INBOUND).status_code == 200
