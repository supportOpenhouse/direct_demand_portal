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


def test_call_log_filters_bind_every_value():
    """The clause is interpolated into the SQL, so anything user-supplied must arrive
    as a bind param — and an unfiltered list must not emit a dangling WHERE."""
    from app.routers.bonvoice import call_log_filters

    assert call_log_filters(None, None) == ("", {})
    clause, params = call_log_filters("98460'; drop table leads --", True)
    assert "drop table" not in clause and clause.startswith(" WHERE ")
    assert clause.count(" AND ") == 1
    assert params == {"q": "%98460'; drop table leads --%", "answered": True}
    # answered=False is a real filter, not an absent one
    assert call_log_filters(None, False)[1] == {"answered": False}


def test_pulled_record_maps_onto_the_callback_shape():
    """/crm/callrecords/ describes the same call as the webhook but with its own
    casing and no lifecycle callType — the mapping is what lets both feeds upsert
    onto the same row."""
    from app.routers.bonvoice import record_to_callback

    rec = {"callID": "c99", "source": "9846098460", "destination": "9812345678",
           "status": "ANSWERED", "startTime": "2026-08-01T10:00:00",
           "endTime": "2026-08-01T10:02:00", "resourceurl": "https://rec/c99.mp3",
           "someUnmappedField": "kept"}
    m = record_to_callback(rec)
    assert m["callID"] == "c99"
    assert m["Leg"] == "A"                      # records don't name a leg
    assert m["SourceNumber"] == "9846098460" and m["DestinationNumber"] == "9812345678"
    assert m["ResourceURL"] == "https://rec/c99.mp3"   # the recording, lowercased
    assert m["StartTime"] and m["EndTime"]
    assert m["callType"] == "1"                 # ANSWERED → connected
    assert m["someUnmappedField"] == "kept"     # rides along into raw
    # a missed call must not synthesise "answered"
    assert record_to_callback({"callID": "c1", "status": "NO ANSWER"})["callType"] == ""


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


def test_base_url_survives_blank_and_scheme_less_config(monkeypatch):
    """An env var set to "" overrides the default, and ops handed out a bare host
    ("pbx.bonvoice.com"). Both produced httpx's "missing an 'http://' protocol"."""
    s = config.get_settings()
    for raw, expected in [
        ("", "https://backend.pbx.bonvoice.com"),
        ("   ", "https://backend.pbx.bonvoice.com"),
        ("pbx.bonvoice.com", "https://pbx.bonvoice.com"),
        ("pbx.bonvoice.com/", "https://pbx.bonvoice.com"),
        ("https://backend.pbx.bonvoice.com/", "https://backend.pbx.bonvoice.com"),
        ("http://localhost:9000", "http://localhost:9000"),
    ]:
        monkeypatch.setattr(s, "BONVOICE_BASE_URL", raw)
        assert s.bonvoice_base == expected, f"{raw!r} -> {s.bonvoice_base}"
        assert s.bonvoice_base.startswith(("http://", "https://"))


class _FakeResp:
    """Minimal httpx.Response stand-in — only .json() is read."""
    def __init__(self, body): self._b = body
    def json(self):
        import json as _j
        if isinstance(self._b, str):
            return _j.loads(self._b)  # raises ValueError on non-JSON, like httpx
        return self._b


def test_rejection_is_detected_despite_http_200():
    """Bonvoice answers 200 for BOTH outcomes. Reading only the status code reported
    every rejection as "ringing" — the caller waited for a call that never came."""
    from app.routers.bonvoice import _rejection_reason

    # real observed rejection body
    assert _rejection_reason(_FakeResp({"error": "DID is not configured"})) == "DID is not configured"
    # documented success body
    assert _rejection_reason(_FakeResp(
        {"responseCode": 200, "responseDescription": "Success", "responseType": "Success"})) is None
    # an error surfaced through responseType instead
    assert _rejection_reason(_FakeResp(
        {"responseType": "Error", "responseDescription": "Invalid DID or route"})) == "Invalid DID or route"
    # unparseable → assume accepted; the call may have gone out, and a false failure
    # is worse than silence
    assert _rejection_reason(_FakeResp("<html>502</html>")) is None
    assert _rejection_reason(_FakeResp([1, 2, 3])) is None
