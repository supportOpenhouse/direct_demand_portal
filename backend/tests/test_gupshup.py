import uuid

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
def _no_database(monkeypatch):
    """Webhook tests post real-shaped callbacks; _persist must never see the prod engine."""
    monkeypatch.setattr("app.routers.gupshup.neon_engine", lambda: None)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Settings load the developer's real backend/.env, so a filled-in GUPSHUP_* would
    otherwise decide these tests — and a configured send would fire real WhatsApp
    traffic. Each test starts from unconfigured and opts in explicitly.

    GOOGLE_OAUTH_CLIENT_ID is cleared for the same reason: setting it in .env flips
    auth_enabled on, and every authed endpoint here starts answering 401 instead of
    what the test is actually about."""
    s = config.get_settings()  # lru_cached: the same object the app reads
    for key in ("GUPSHUP_WEBHOOK_SECRET", "GUPSHUP_TEMPLATE_WEBHOOK_SECRET", "GUPSHUP_API_KEY",
                "GUPSHUP_SOURCE_NUMBER", "GUPSHUP_APP_NAME", "GUPSHUP_TEMPLATE_API_KEY",
                "GUPSHUP_TEMPLATE_SOURCE_NUMBER", "GUPSHUP_TEMPLATE_APP_NAME", "GOOGLE_OAUTH_CLIENT_ID"):
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


# --- the template-campaign app's callback -------------------------------------------

def test_template_webhook_accepts_both_callback_types_and_stamps_the_app():
    """Same contract as the chat webhook (empty 2xx), but every entry carries
    app='template' so _persist writes source_app on the inbound row."""
    _RECENT.clear()
    assert client.get("/v1/gupshup/template-webhook").json() == {"status": "ok"}
    for payload in (INBOUND, EVENT):
        r = client.post("/v1/gupshup/template-webhook", json=payload)
        assert r.status_code == 200 and r.content == b""
    assert [i["app"] for i in _RECENT] == ["template", "template"]
    # the chat webhook stays unstamped (NULL = main app)
    client.post("/v1/gupshup/webhook", json=INBOUND)
    assert _RECENT[0]["app"] is None


def test_template_webhook_has_its_own_token(monkeypatch):
    s = config.get_settings()
    monkeypatch.setattr(s, "GUPSHUP_TEMPLATE_WEBHOOK_SECRET", "t3mpl")
    monkeypatch.setattr(s, "GUPSHUP_WEBHOOK_SECRET", "chat-secret")
    assert client.post("/v1/gupshup/template-webhook", json=INBOUND).status_code == 403
    # the CHAT secret must not open the template URL
    assert client.post("/v1/gupshup/template-webhook?token=chat-secret", json=INBOUND).status_code == 403
    assert client.post("/v1/gupshup/template-webhook?token=t3mpl", json=INBOUND).status_code == 200
    assert client.get("/v1/gupshup/template-webhook?token=t3mpl").status_code == 200


def test_template_webhook_refuses_in_prod_without_a_secret(monkeypatch):
    """Unlike the older chat webhook, an unset secret is not 'open' in prod."""
    monkeypatch.setattr(config.get_settings(), "APP_ENV", "prod")
    assert client.post("/v1/gupshup/template-webhook", json=INBOUND).status_code == 503


# --- the paged conversation list -----------------------------------------------------

def test_the_thread_list_and_its_counts_are_scoped_like_every_other_read():
    """An RM must see — and count — only their own conversations. Both the page and
    both totals go through _scoped (→ _thread_scope); a count that skipped it would
    tell an RM how many conversations exist in total."""
    import inspect

    from app.routers import gupshup
    src = inspect.getsource(gupshup.gupshup_threads)
    assert src.count("_scoped(") == 3, "page + total + convertible total"
    assert "_scoped(" in inspect.getsource(gupshup.gupshup_convertible)


def test_the_thread_page_size_is_bounded():
    from app.routers.gupshup import THREADS_PAGE_MAX
    assert THREADS_PAGE_MAX <= 200


def test_the_lead_transcript_is_scoped_by_the_lead_not_the_thread():
    """The popup's transcript follows LEAD visibility (_role_scope): the lead's RM sees
    it even when the WhatsApp thread is unowned, and an RM who can't open the lead
    gets nothing. _thread_scope here would hide it from exactly the lead's RM."""
    import inspect

    from app.routers import gupshup
    src = inspect.getsource(gupshup.lead_transcript)
    assert "_role_scope(user)" in src
    assert "_thread_scope" not in src.split('"""', 2)[2]  # code, not the docstring
    route = next(r for r in gupshup.router.routes if r.path == "/gupshup/lead/{lead_id}/transcript")
    assert route.methods == {"GET"}


# --- replying from the number the customer wrote to (Task 8) -------------------------

def test_a_reply_goes_out_through_the_number_the_customer_wrote_to():
    import inspect

    from app.routers import gupshup
    src = inspect.getsource(gupshup._reply_app)
    assert "direction == \"in\"" in src.replace("'", '"') and "source_app" in src
    send = inspect.getsource(gupshup.gupshup_send)
    assert "_reply_app(" in send and "GUPSHUP_TEMPLATE_API_KEY" in send


class _R:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _C:
    """Answers by statement shape; records writes. No database."""

    def __init__(self, last_inbound_app, rows=()):
        self.app, self.rows, self.writes = last_inbound_app, rows, []

    async def execute(self, stmt, params=None):
        cols = len(getattr(stmt, "selected_columns", []) or [])
        if cols == 1 and "source_app" in str(stmt):  # _reply_app
            return _R([(self.app,)] if self.app != "none" else [])
        if cols > 1 and "FROM wa_messages" in str(stmt):  # the message list
            return _R(self.rows)
        if cols == 0 and hasattr(stmt, "table"):
            self.writes.append(stmt)
        return _R()


class _E:
    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return self._ctx()

    begin = connect

    def _ctx(self):
        conn = self.conn

        class X:
            async def __aenter__(s):
                return conn

            async def __aexit__(s, *a):
                return False
        return X()


def _wire(monkeypatch, conn, app_creds=True):
    """Fake DB + a MockTransport for httpx — the real Gupshup is unreachable from these tests."""
    import httpx

    from app.routers import gupshup
    s = config.get_settings()
    for k, v in (("GUPSHUP_API_KEY", "chat-key"), ("GUPSHUP_SOURCE_NUMBER", "911111111111"),
                 ("GUPSHUP_APP_NAME", "ChatApp"), ("GUPSHUP_TEMPLATE_API_KEY", "tpl-key"),
                 ("GUPSHUP_TEMPLATE_SOURCE_NUMBER", "912222222222"), ("GUPSHUP_TEMPLATE_APP_NAME", "OHTemplates")):
        monkeypatch.setattr(s, k, v if app_creds or not k.startswith("GUPSHUP_TEMPLATE") else "")
    monkeypatch.setattr(gupshup, "neon_engine", lambda: _E(conn))
    seen = []
    real = httpx.AsyncClient

    def handler(req):
        seen.append(req)
        return httpx.Response(202, json={"status": "submitted", "messageId": "m9"})
    monkeypatch.setattr(gupshup.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen


ADMIN = {"email": "a@openhouse.in", "name": "Admin", "role": "admin"}


async def test_a_template_number_customer_is_answered_from_the_template_app(monkeypatch):
    from urllib.parse import parse_qs

    from app.routers import gupshup
    conn = _C("template")
    seen = _wire(monkeypatch, conn)
    await gupshup.gupshup_send(gupshup.SendRequest(phone="9876543210", text="hi"), ADMIN)
    form = parse_qs(seen[0].content.decode())
    assert len(seen) == 1 and seen[0].headers["apikey"] == "tpl-key"
    assert form["source"] == ["912222222222"] and form["src.name"] == ["OHTemplates"]
    assert conn.writes[0].compile().params["source_app"] == "template"


async def test_a_chat_number_customer_is_answered_from_the_chat_app(monkeypatch):
    from urllib.parse import parse_qs

    from app.routers import gupshup
    conn = _C(None)
    seen = _wire(monkeypatch, conn)
    await gupshup.gupshup_send(gupshup.SendRequest(phone="9876543210", text="hi"), ADMIN)
    assert seen[0].headers["apikey"] == "chat-key"
    assert parse_qs(seen[0].content.decode())["source"] == ["911111111111"]
    assert conn.writes[0].compile().params["source_app"] is None


async def test_a_template_reply_without_template_config_is_a_503_and_sends_nothing(monkeypatch):
    from app.routers import gupshup
    seen = _wire(monkeypatch, _C("template"), app_creds=False)
    with pytest.raises(Exception) as e:
        await gupshup.gupshup_send(gupshup.SendRequest(phone="9876543210", text="hi"), ADMIN)
    assert e.value.status_code == 503 and "GUPSHUP_TEMPLATE_API_KEY" in e.value.detail and seen == []


async def test_messages_say_which_app_each_came_through_and_which_one_replies(monkeypatch):
    from datetime import datetime, timezone

    from app.routers import gupshup
    row = {"id": uuid.uuid4(), "direction": "in", "phone": "919876543210", "name": "R", "body": "x",
           "msg_type": "text", "status": None, "author": None, "media_url": None, "media_expiry": None,
           "media_name": None, "source_app": "template", "created_at": datetime.now(timezone.utc)}
    conn = _C("template", rows=[row])
    _wire(monkeypatch, conn)
    one = await gupshup.gupshup_messages(phone="9876543210", user=ADMIN)
    assert one["reply_app"] == "template" and one["items"][0]["source_app"] == "template"
    conn.app = "none"
    assert (await gupshup.gupshup_messages(phone="9876543210", user=ADMIN))["reply_app"] == "chat"
    assert "reply_app" not in await gupshup.gupshup_messages(phone=None, user=ADMIN)


def test_the_24h_window_comment_no_longer_claims_gupshup_says_so_in_the_response():
    import inspect

    from app.routers import gupshup
    src = inspect.getsource(gupshup.gupshup_send)
    assert "Gupshup says so here" not in src and "contract Delta 15" in src


def test_button_taps_render_as_their_text():
    from app.routers.gupshup import _text_of
    tap = {"text": "Yes", "type": "button", "postbackText": "x"}
    assert _text_of(tap, "quick_reply") == "Yes"
    assert _text_of(tap, "text") == "Yes"
    assert _text_of({"title": "No"}, "button_reply") == "No"


def test_message_events_match_our_id_or_the_whatsapp_id_and_only_move_forward():
    from app.routers.gupshup import WA_EVENT_SQL
    sql = WA_EVENT_SQL.text
    assert "gupshup_id = :key OR whatsapp_id = CAST(:wa_id AS text)" in sql
    assert "COALESCE(whatsapp_id, CAST(:learn AS text))" in sql
    assert ":rank > (CASE status" in sql, "a late 'delivered' must never overwrite 'read'"


def test_a_v3_payload_is_flagged(caplog):
    with caplog.at_level("WARNING", logger="gupshup"):
        r = client.post("/v1/gupshup/webhook", json={"object": "whatsapp_business_account", "entry": []})
    assert r.status_code == 200
    assert "version 2" in caplog.text


def test_a_retried_inbound_callback_is_stored_once():
    import inspect

    from app.routers import gupshup
    src = inspect.getsource(gupshup._persist)
    assert "INBOUND_EXISTS_SQL" in src
    assert "direction = 'in'" in gupshup.INBOUND_EXISTS_SQL.text and "gupshup_id = :id" in gupshup.INBOUND_EXISTS_SQL.text


def test_an_unmatched_sync_event_is_retried_once():
    import inspect

    from app.routers import gupshup
    src = inspect.getsource(gupshup._persist)
    assert "EVENT_RETRY_SECONDS" in src and gupshup.EVENT_RETRY_SECONDS == 10


async def test_persist_retries_an_unmatched_enqueued_event_once_after_the_delay(monkeypatch):
    from app.routers import gupshup
    calls, sleeps = [], []

    async def fake_apply(engine, ev):
        calls.append(ev["type"])
        return 0

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(gupshup, "neon_engine", lambda: object())
    monkeypatch.setattr(gupshup, "_apply_event", fake_apply)
    monkeypatch.setattr(gupshup.asyncio, "sleep", fake_sleep)
    ev = {"type": "enqueued", "id": "g1", "payload": {"whatsappMessageId": "w1"}}
    await gupshup._persist({"type": "message-event", "body": {"payload": ev}})
    assert calls == ["enqueued", "enqueued"] and sleeps == [10]
    calls.clear()
    sleeps.clear()
    await gupshup._persist({"type": "message-event", "body": {"payload": {**ev, "type": "delivered"}}})
    assert calls == ["delivered"] and sleeps == []  # only enqueued/failed are retried


def test_the_two_views_split_by_the_app_the_customer_wrote_to():
    import inspect

    from app.routers import gupshup
    src = inspect.getsource(gupshup._view_filter)
    assert "source_app" in src and "'template'" in src.replace('"', "'")
    assert "direction" in src, "a view is defined by INBOUND messages on that app"
    assert "both" in inspect.getsource(gupshup.gupshup_threads)


def test_the_view_filter_does_not_correlate_its_subquery_away():
    """Same table inside and outside: without an alias SQLAlchemy auto-correlates the inner SELECT and
    drops its FROM, turning the filter into `phone IN (SELECT phone)` — every conversation in both views."""
    from sqlalchemy.dialects import postgresql

    from app.routers import gupshup
    from app.models import WaMessage
    from sqlalchemy import select
    for view in ("chat", "template"):
        sql = str(select(WaMessage.phone).where(gupshup._view_filter(view)).compile(dialect=postgresql.dialect()))
        assert sql.count("FROM wa_messages") == 2, sql
    tpl = str(select(WaMessage.phone).where(gupshup._view_filter("template")).compile(dialect=postgresql.dialect()))
    chat = str(select(WaMessage.phone).where(gupshup._view_filter("chat")).compile(dialect=postgresql.dialect()))
    assert "IS NULL" in chat and "IS NULL" not in tpl


def test_both_endpoints_take_a_view_and_default_to_chat():
    import inspect

    from app.routers import gupshup
    for fn in (gupshup.gupshup_threads, gupshup.gupshup_convertible):
        p = inspect.signature(fn).parameters["view"]
        assert p.default == "chat"
    assert inspect.getsource(gupshup.gupshup_convertible).count("_view_filter(view)") == 1
    assert inspect.getsource(gupshup.gupshup_threads).count("_view_filter(view)") == 3


# --- opt-out (contract §7, Delta 12) --------------------------------------------------

def test_stop_means_opt_out():
    from app.routers.gupshup import OPT_OUT_SQL, is_stop
    for s in ("STOP", " stop ", "Stop."):
        assert is_stop(s), s
    for s in ("don't stop", "stopped by later", "", None):
        assert not is_stop(s), s
    sql = OPT_OUT_SQL.text
    assert "'opted_out'" in sql and "ON CONFLICT (phone10)" in sql and "marked_by = :by" in sql
    assert "IS DISTINCT FROM 'rejected'" in sql, "an opt-out must not un-reject a number"
    assert "assigned_to = NULL" not in sql.split("ON CONFLICT")[1], "keep the owner"


def test_metas_preference_event_is_read_from_the_documented_shape():
    """contract §7 — Gupshup v2 `preference-event`, payload copied from Gupshup's BSUID page."""
    from app.routers.gupshup import opt_out_changes
    payload = {"type": "user_preferences", "payload": {"user_preferences": [
        {"wa_id": "919297545638", "detail": "User requested to stop marketing messages",
         "category": "marketing_messages", "value": "stop", "timestamp": 1},
        {"wa_id": "919876543210", "category": "marketing_messages", "value": "resume"},
        {"wa_id": "919111111111", "category": "some_future_category", "value": "stop"},
        {"wa_id": "12", "category": "marketing_messages", "value": "stop"},
    ]}}
    assert opt_out_changes(payload) == [("9297545638", "stop"), ("9876543210", "resume")]
    assert opt_out_changes({}) == [] and opt_out_changes({"payload": {}}) == []


def test_resume_only_undoes_an_opt_out_that_meta_made():
    """A Meta 'resume' must not cancel a STOP the person typed to us, or a hand-made opt-out."""
    from app.routers.gupshup import META_STOP_BY, OPT_IN_SQL
    sql = OPT_IN_SQL.text
    assert "tag = 'opted_out'" in sql and f"marked_by = '{META_STOP_BY}'" in sql
    assert "tag = NULL" in sql


def test_a_131050_failure_opts_the_number_out():
    """Meta: 'Do not retry … they have chosen to stop receiving marketing messages' (contract §3.5)."""
    import inspect
    from app.routers import gupshup
    assert gupshup.OPTED_OUT_CODE == 131050
    src = inspect.getsource(gupshup._apply_event)
    assert "OPTED_OUT_CODE" in src and "OPT_OUT_SQL" in src and "META_STOP_BY" in src


def test_persist_wires_a_typed_stop_and_the_preference_event():
    import inspect
    from app.routers import gupshup
    src = inspect.getsource(gupshup._persist)
    assert "is_stop(" in src and "STOP_REPLY_BY" in src
    assert '"preference-event"' in src and "opt_out_changes(" in src and "OPT_IN_SQL" in src


def test_the_mark_menu_can_pick_opted_out():
    from app.routers.gupshup import MarkRequest
    assert MarkRequest(phone="9876543210", tag="opted_out").tag == "opted_out"


def test_accept_hands_a_preference_event_to_persist(monkeypatch):
    """_accept filters nothing by type: a preference-event body reaches _persist."""
    from app.routers import gupshup
    seen = []

    async def fake(entry):
        seen.append(entry["type"])
    monkeypatch.setattr(gupshup, "_persist", fake)
    body = {"type": "preference-event", "payload": {"type": "user_preferences", "payload": {"user_preferences": []}}}
    assert client.post("/v1/gupshup/template-webhook", json=body).status_code == 200
    assert seen == ["preference-event"]


# --- final fix round: STOP button, no re-stamp, opted_out treated like rejected -------

class _PRes:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self.rows)


class _PConn:
    def __init__(self, answer=None):
        self.calls, self.answer = [], answer or (lambda s, p: _PRes())

    async def execute(self, stmt, params=None):
        self.calls.append((stmt, params))
        return self.answer(stmt, params)


class _PCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class _PEng:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return _PCtx(self.conn)

    connect = begin


def _tap(text, outer="quick_reply"):
    return {"type": "message", "app": "template", "body": {"type": "message", "payload": {
        "id": "in-1", "source": "919876543210", "type": outer,
        "payload": {"text": text, "type": "button", "postbackText": "p"},
        "sender": {"phone": "919876543210", "name": "R"}, "context": {"gsId": "g1", "id": "w1"}}}}


def _typed(text):
    return {"type": "message", "app": None, "body": {"type": "message", "payload": {
        "id": "in-2", "source": "919876543210", "type": "text", "payload": {"text": text},
        "sender": {"phone": "919876543210", "name": "R"}}}}


@pytest.mark.parametrize("entry,by", [
    (_tap("Stop promotions"), "STOP button"),          # G-5: Meta's opt-out button on a marketing template
    (_tap("STOP", outer="text"), "STOP button"),        # Doc B's tap shape (contract §6.2)
    (_typed("stop"), "STOP reply"),
    (_tap("Yes, call me"), None),
    (_typed("Stop promotions"), None),                  # typed text keeps the exact-word rule
    (_typed("don't stop"), None),
])
async def test_a_stop_button_tap_opts_out_and_typed_text_keeps_the_exact_rule(monkeypatch, entry, by):
    from app.routers import gupshup
    conn = _PConn()
    monkeypatch.setattr(gupshup, "neon_engine", lambda: _PEng(conn))
    await gupshup._persist(entry)
    opted = [p for s, p in conn.calls if s is gupshup.OPT_OUT_SQL]
    assert opted == ([{"p": "9876543210", "by": by}] if by else [])


def test_is_stop_button_reads_the_first_word():
    from app.routers.gupshup import is_stop_button
    for s in ("Stop promotions", "STOP", "stop-offers", " Stop."):
        assert is_stop_button(s), s
    for s in ("Don't stop", "Stopped", "Yes", "", None):
        assert not is_stop_button(s), s


def test_an_opt_out_is_never_re_stamped():
    """G-13: a Meta stop re-stamping an admin's / typed-STOP opt-out as Meta's let Meta's next resume undo it."""
    from app.routers.gupshup import OPT_OUT_SQL
    sql = " ".join(OPT_OUT_SQL.text.split())
    assert "WHERE wa_contacts.tag IS DISTINCT FROM 'rejected' AND wa_contacts.tag IS DISTINCT FROM 'opted_out'" in sql


def test_the_bell_and_create_leads_skip_opted_out_like_rejected():
    """F-4: opted_out is a decision not to work the number, like rejected."""
    import inspect

    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from app.models import WaMessage
    from app.routers import gupshup
    assert gupshup.DECLINED_TAGS == ("rejected", "opted_out")
    assert "tags.get(p10) in DECLINED_TAGS" in inspect.getsource(gupshup.gupshup_pending)
    sql = str(select(WaMessage.phone).where(gupshup._NOT_DECLINED).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "NOT IN (SELECT wa_contacts.phone10" in sql and "wa_contacts.tag IN ('rejected', 'opted_out')" in sql
    assert inspect.getsource(gupshup.gupshup_convertible).count("_NOT_DECLINED") == 1
    assert inspect.getsource(gupshup.gupshup_threads).count("_NOT_DECLINED") == 1, "convertible_total matches the list"


async def test_the_pending_bell_drops_an_opted_out_conversation(monkeypatch):
    from datetime import datetime, timezone

    from app.routers import gupshup
    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    msgs = [{"phone": "919876543210", "direction": "in", "name": "A", "created_at": now},
            {"phone": "919876543211", "direction": "in", "name": "B", "created_at": now},
            {"phone": "919876543212", "direction": "in", "name": "C", "created_at": now}]
    tags = [{"phone10": "9876543210", "tag": "opted_out", "assigned_to": None},
            {"phone10": "9876543211", "tag": "rejected", "assigned_to": None}]

    def answer(stmt, p):
        sql = str(stmt)
        if "wa_contacts" in sql:
            return _PRes(tags)
        if "FROM leads" in sql:
            return _PRes([])
        return _PRes(msgs)
    monkeypatch.setattr(gupshup, "neon_engine", lambda: _PEng(_PConn(answer)))
    out = await gupshup.gupshup_pending({"role": "admin", "email": "a@x"})
    assert [i["phone"] for i in out["items"]] == ["919876543212"]


@pytest.mark.parametrize("tag,assigns", [("opted_out", False), ("rejected", False), ("buyer", True)])
async def test_marking_opted_out_never_assigns_an_owner(monkeypatch, tag, assigns):
    from app.routers import gupshup
    from app.services import wa_assign
    asked = []

    async def assign(conn, p10):
        asked.append(p10)
        return "Asha"
    monkeypatch.setattr(wa_assign, "assign_if_unassigned", assign)
    monkeypatch.setattr(gupshup, "neon_engine", lambda: _PEng(_PConn()))
    await gupshup.gupshup_mark(gupshup.MarkRequest(phone="9876543210", tag=tag), {"role": "admin", "email": "a@x"})
    assert bool(asked) is assigns
