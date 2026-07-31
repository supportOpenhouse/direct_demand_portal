import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config
from app.routers.bonvoice import _digits, _mask, lead_id_from, parse_body, router

app = FastAPI()
app.include_router(router, prefix="/v1")
client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Settings read the developer's real ../.env. Without this, filled-in BONVOICE_*
    values would decide these tests — and a configured account would place REAL CALLS."""
    s = config.get_settings()
    for key in ("BONVOICE_DID", "BONVOICE_TOKEN", "BONVOICE_USERNAME",
                "BONVOICE_PASSWORD", "BONVOICE_WEBHOOK_SECRET"):
        monkeypatch.setattr(s, key, "")


def test_digits_accepts_every_documented_format():
    """Bonvoice accepts 9846098460 / 09846098460 / 919846098460 / +919846098460 and
    Indian numbers only — all of them reduce to the same last 10 digits."""
    for raw in ("9846098460", "09846098460", "919846098460", "+919846098460",
                "+91 98460 98460".replace("98460 98460", "98460 98460")):
        assert len(_digits(raw)) == 10
    assert _digits("+919846098460") == "9846098460"
    assert _digits("12345") == ""      # too short to be a mobile
    assert _digits(None) == ""


def test_mask_keeps_only_the_last_four():
    assert _mask("9846098460") == "••••••8460"
    assert _mask("") == "—"


def test_parse_body_handles_json_and_form():
    """The callback format is an account setting, so both must work — including a
    form-encoded body sent with a JSON content type."""
    assert parse_body(b'{"callID":"c1","Leg":"A"}', "application/json") == {"callID": "c1", "Leg": "A"}
    assert parse_body(b"callID=c1&Leg=B", "application/x-www-form-urlencoded") == {"callID": "c1", "Leg": "B"}
    assert parse_body(b"callID=c1&Leg=B", "application/json") == {"callID": "c1", "Leg": "B"}
    assert parse_body(b"", "application/json") == {}


def test_lead_id_survives_both_callback_encodings():
    """callBackParams is an object on JSON callbacks and a JSON string on form-encoded
    ones. This is the only link between a call log and its lead — if it fails to parse
    the log is orphaned."""
    uid = "3f1a9c62-1f4e-4c8e-9f2a-6b5d7c8e9a01"
    assert str(lead_id_from({"lead_id": uid})) == uid
    assert str(lead_id_from('{"lead_id": "%s"}' % uid)) == uid
    assert lead_id_from(None) is None
    assert lead_id_from("not json") is None
    assert lead_id_from({"lead_id": "nonsense"}) is None


def test_webhook_always_acks_200():
    """A non-2xx makes the PBX retry; the callback fires up to 6 times per call."""
    for body, ctype in [
        (b'{"callID":"c1","Leg":"A","callType":"0"}', "application/json"),
        (b"callID=c1&Leg=B&callType=2", "application/x-www-form-urlencoded"),
        (b"<xml>surprise</xml>", "application/json"),
        (b"", "application/json"),
    ]:
        r = client.post("/v1/bonvoice/webhook", content=body, headers={"Content-Type": ctype})
        assert r.status_code == 200, f"{ctype} body was rejected"


def test_webhook_token_enforced_when_set(monkeypatch):
    monkeypatch.setattr(config.get_settings(), "BONVOICE_WEBHOOK_SECRET", "s3cret")
    assert client.post("/v1/bonvoice/webhook", json={"callID": "c1"}).status_code == 403
    assert client.post("/v1/bonvoice/webhook?token=nope", json={"callID": "c1"}).status_code == 403
    assert client.post("/v1/bonvoice/webhook?token=s3cret", json={"callID": "c1"}).status_code == 200


def test_call_refuses_when_unconfigured():
    """No DID/credentials → a clear 503 rather than an obscure failure at the PBX."""
    r = client.post("/v1/bonvoice/call",
                    json={"lead_id": "3f1a9c62-1f4e-4c8e-9f2a-6b5d7c8e9a01"})
    assert r.status_code == 503
    assert "BONVOICE_DID" in r.json()["detail"]
