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


def test_pulled_outgoing_records_keep_our_own_number():
    """Bonvoice fills DisplayNumber only on incoming records. On outgoing ones it is
    null and the RM's handset arrives in `Agent` — reading DisplayNumber alone left
    every outgoing call in the log with no source_number (82 of 157 rows).

    Both payloads below are real shapes from /crm/callrecords/."""
    from app.routers.bonvoice import record_to_callback

    outgoing = record_to_callback({
        "Agent": "8003297088", "DisplayNumber": None, "Customer": "8595594789",
        "StartTime": "2026-07-31 06:23:36 PM", "Status": "ANSWERED",
        "CallDirection": "outgoing", "CallDuration": "3min 57sec", "callID": "x1",
    })
    assert outgoing["SourceNumber"] == "8003297088"     # us
    assert outgoing["DestinationNumber"] == "8595594789"  # the lead

    incoming = record_to_callback({
        "Agent": None, "DisplayNumber": "8065453090", "Customer": "7217031734",
        "StartTime": "2026-07-31 12:18:33 PM", "Status": "NOINPUT",
        "CallDirection": "incoming", "CallDuration": "0 min 0sec", "callID": "x2",
    })
    assert incoming["SourceNumber"] == "7217031734"      # the lead
    assert incoming["DestinationNumber"] == "8065453090"  # our DID

    # `Agent` is a phone number on these records, never a status — falling back to it
    # wrote '9958075070' into agent_status for 58 rows.
    assert outgoing["AgentStatus"] is None
    assert incoming["AgentStatus"] is None


def test_call_log_filters_bind_every_value():
    """The clause is interpolated into the SQL, so anything user-supplied must arrive
    as a bind param — and an unfiltered list must not emit a dangling WHERE."""
    from app.routers.bonvoice import call_log_filters

    assert call_log_filters(None, None) == ("", {})
    clause, params = call_log_filters("98460'; drop table leads --", True)
    assert "drop table" not in clause and clause.startswith(" WHERE ")
    assert clause.count(" AND ") == 1
    assert params["q"] == "%98460'; drop table leads --%" and params["answered"] is True
    # answered=False is a real filter, not an absent one
    assert call_log_filters(None, False)[1] == {"answered": False}


def test_campaign_filter_scopes_the_call_log_without_inlining_the_id():
    """Previous Campaigns reuses this endpoint, so campaign_id joins the same clause
    as a bind param and composes with the other filters."""
    import uuid

    from app.routers.bonvoice import call_log_filters

    cid = uuid.uuid4()
    clause, params = call_log_filters(None, None, cid)
    assert clause == " WHERE c.campaign_id = :campaign_id"
    assert params == {"campaign_id": cid} and str(cid) not in clause

    # composes: campaign + search + answered are ANDed, none of them inlined
    clause, params = call_log_filters("amit", True, cid)
    assert clause.count(" AND ") == 2
    assert params["campaign_id"] == cid and params["q"] == "%amit%"

    # absent campaign stays absent — the Call Log page must not gain a filter
    assert call_log_filters(None, None) == ("", {})


def test_searching_by_phone_matches_every_stored_format():
    """Bonvoice reports '9999799588', users.phone holds '919999999999' and leads.phone
    '+91 99997 99588'. Searching any of those forms has to find the same calls, so the
    comparison runs on the last 10 digits of both sides."""
    from app.routers.bonvoice import call_log_filters

    for typed in ("9999799588", "919999799588", "+91 99997 99588", "0 99997 99588"):
        clause, params = call_log_filters(typed, None)
        assert params["q10"] == "9999799588", f"{typed} normalised to {params.get('q10')}"
        assert clause.count("regexp_replace") == 4   # both call numbers, the DID, the lead
        assert ":q10" in clause and ":q" in clause   # digits OR the plain text search
    # a name search stays a name search — no digits, no phone comparison
    clause, params = call_log_filters("Priya", None)
    assert "q10" not in params and "regexp_replace" not in clause
    # too short to be a mobile: treated as text, not a truncated number
    assert "q10" not in call_log_filters("99997", None)[1]


# One real row from POST /crm/callrecords/, numbers changed. Everything the mapping
# has to cope with is in here: 12-hour local timestamps, no EndTime, no leg, and the
# two parties named Customer/DisplayNumber instead of source/destination.
PULLED_RECORD = {
    "Agent": "09810925822", "eventId": None, "DisplayNumber": "8065453090",
    "Customer": "9220633844", "StartTime": "2026-08-04 12:43:30 PM",
    "DataSource": "Bonvoice", "Status": "ANSWERED", "CallDirection": "outgoing",
    "CallDuration": "3min 12sec",
    "callID": "1785827610.7806364-8065453090-9220633844-20260804-124330",
    "CallRecord": "https://backend.pbx.bonvoice.com/externalapi/v1/8/downloadvoice/x/",
}


def test_pulled_record_maps_onto_the_callback_shape():
    """/crm/callrecords/ describes the same call as the webhook with different names
    and no lifecycle callType — the mapping is what lets both feeds upsert one row."""
    from app.routers.bonvoice import record_to_callback

    m = record_to_callback(PULLED_RECORD)
    assert m["callID"] == PULLED_RECORD["callID"]
    assert m["Leg"] == "A"                          # records don't name a leg
    # outbound: we dial out from the DID to the customer; inbound is the reverse
    assert (m["SourceNumber"], m["DestinationNumber"]) == ("8065453090", "9220633844")
    inbound = record_to_callback({**PULLED_RECORD, "CallDirection": "incoming"})
    assert (inbound["SourceNumber"], inbound["DestinationNumber"]) == ("9220633844", "8065453090")
    assert m["ResourceURL"] == PULLED_RECORD["CallRecord"]
    assert m["callType"] == "1"                     # ANSWERED → connected
    assert m["DataSource"] == "Bonvoice"            # unmapped fields ride along into raw


def test_pulled_timestamps_are_read_as_indian_local_time():
    """'2026-08-04 12:43:30 PM' is IST and unlabelled — stored naive it would land in
    a timestamptz column as UTC and read 5½ hours early. End time is start + duration,
    the record carrying no EndTime of its own."""
    from app.routers.bonvoice import record_to_callback

    m = record_to_callback(PULLED_RECORD)
    assert m["StartTime"] == "2026-08-04T12:43:30+05:30"
    assert m["EndTime"] == "2026-08-04T12:46:42+05:30"   # +3min 12sec


def test_pulled_record_edge_cases():
    from app.routers.bonvoice import record_to_callback

    # a missed call must not synthesise "answered"
    assert record_to_callback({**PULLED_RECORD, "Status": "NOANSWER"})["callType"] == ""
    # a zero-second call has a recording url that serves "File not exist"
    assert record_to_callback({**PULLED_RECORD, "CallDuration": "0 min 0sec"})["ResourceURL"] is None
    # nothing parseable → no invented timestamps, and the row still maps
    bare = record_to_callback({"callID": "c1"})
    assert bare["StartTime"] is None and bare["EndTime"] is None and bare["Leg"] == "A"


def test_call_records_envelope_is_unwrapped():
    """The response is {"call_count": n, "call_logs": [...]} — miss that key and a
    working sync silently stores nothing."""
    from app.routers.bonvoice import log_records

    assert log_records({"call_count": 2, "call_logs": [PULLED_RECORD, PULLED_RECORD]}) == \
        [PULLED_RECORD, PULLED_RECORD]
    assert log_records({"call_count": 0, "call_logs": []}) == []


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
