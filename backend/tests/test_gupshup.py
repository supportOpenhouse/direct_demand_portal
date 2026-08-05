import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config
from app.routers.gupshup import _RECENT, normalize_phone, parse_body, router

# bare app — the real one's lifespan wants a DB; the router is what's under test
app = FastAPI()
app.include_router(router, prefix="/v1")
client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Settings load the developer's real ../.env, so a filled-in GUPSHUP_* would
    otherwise decide these tests — and a configured send would fire real WhatsApp
    traffic. Each test starts from unconfigured and opts in explicitly.

    GOOGLE_OAUTH_CLIENT_ID is cleared for the same reason: setting it in .env flips
    auth_enabled on, and every authed endpoint here starts answering 401 instead of
    what the test is actually about."""
    s = config.get_settings()  # lru_cached: the same object the app reads
    for key in ("GUPSHUP_WEBHOOK_SECRET", "GUPSHUP_API_KEY", "GUPSHUP_SOURCE_NUMBER",
                "GUPSHUP_APP_NAME", "GOOGLE_OAUTH_CLIENT_ID"):
        monkeypatch.setattr(s, key, "")

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


def test_normalize_phone():
    assert normalize_phone("9953998821") == "919953998821"   # bare Indian mobile
    assert normalize_phone("+91 99539 98821") == "919953998821"
    assert normalize_phone("919953998821") == "919953998821"  # already prefixed
    assert normalize_phone(None) == ""


def test_send_refuses_when_unconfigured():
    """No API key → a clear 503, not an obscure failure against Gupshup."""
    r = client.post("/v1/gupshup/send", json={"phone": "9953998821", "text": "hi"})
    assert r.status_code == 503
    assert "GUPSHUP_API_KEY" in r.json()["detail"]


def test_send_rejects_empty_text():
    r = client.post("/v1/gupshup/send", json={"phone": "9953998821", "text": ""})
    assert r.status_code == 422


def test_token_enforced_when_configured(monkeypatch):
    from app import config

    monkeypatch.setattr(config.get_settings(), "GUPSHUP_WEBHOOK_SECRET", "s3cret")
    assert client.post("/v1/gupshup/webhook", json=INBOUND).status_code == 403
    assert client.post("/v1/gupshup/webhook?token=wrong", json=INBOUND).status_code == 403
    assert client.post("/v1/gupshup/webhook?token=s3cret", json=INBOUND).status_code == 200
