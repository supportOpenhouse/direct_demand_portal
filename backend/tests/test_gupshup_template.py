"""The one call to Gupshup's template API — always against httpx.MockTransport, never the network."""
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import get_settings
from app.services import gupshup_template as gt


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "GUPSHUP_TEMPLATE_API_KEY", "k")
    monkeypatch.setattr(s, "GUPSHUP_TEMPLATE_SOURCE_NUMBER", "918888888888")
    monkeypatch.setattr(s, "GUPSHUP_TEMPLATE_APP_NAME", "OHTemplates")  # Gupshup app names have no spaces


def _fake(monkeypatch, handler):
    seen = []

    def transport(req):
        seen.append(req)
        return handler(req)
    monkeypatch.setattr(gt, "_client", lambda: httpx.AsyncClient(
        base_url="https://api.gupshup.io", transport=httpx.MockTransport(transport)))
    return seen


async def test_sends_one_template_message_from_the_template_app(monkeypatch):
    seen = _fake(monkeypatch, lambda r: httpx.Response(202, json={"status": "success", "messageId": "m1"}))
    r = await gt.send_template("9876543210", "tpl-1", ["Rahul", "Noida"])
    assert r == {"ok": True, "message_id": "m1", "status": 202}
    form = parse_qs(seen[0].content.decode())
    assert seen[0].url.path == "/wa/api/v1/template/msg"
    assert seen[0].headers["apikey"] == "k"
    assert seen[0].headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert form["source"] == ["918888888888"] and form["destination"] == ["919876543210"]
    assert form["src.name"] == ["OHTemplates"] and form["channel"] == ["whatsapp"]
    assert json.loads(form["template"][0]) == {"id": "tpl-1", "params": ["Rahul", "Noida"]}


async def test_params_are_sent_as_strings(monkeypatch):
    seen = _fake(monkeypatch, lambda r: httpx.Response(202, json={"status": "submitted", "messageId": "m"}))
    await gt.send_template("9876543210", "t", [5, None])
    assert json.loads(parse_qs(seen[0].content.decode())["template"][0])["params"] == ["5", "None"]


async def test_a_2xx_with_an_error_status_is_a_failure(monkeypatch):
    # Review Focus #2
    _fake(monkeypatch, lambda r: httpx.Response(202, json={"status": "error", "message": "Template not found"}))
    assert await gt.send_template("9876543210", "tpl-x", []) == {"ok": False, "error": "Template not found", "status": 202}


async def test_a_bad_destination_fails_only_that_recipient(monkeypatch):
    _fake(monkeypatch, lambda r: httpx.Response(400, json={"status": "error", "message": "Invalid Destination"}))
    assert await gt.send_template("9876543210", "t", []) == {"ok": False, "error": "Invalid Destination", "status": 400}


async def test_a_non_json_4xx_falls_back_to_the_body_text(monkeypatch):
    _fake(monkeypatch, lambda r: httpx.Response(401, text="Authentication Failed"))
    r = await gt.send_template("9876543210", "t", [])
    assert r["error"] == "Authentication Failed" and r["status"] == 401


@pytest.mark.parametrize("code,message", [(401, "Authentication Failed"), (403, "Forbidden"),
                                          (400, "Invalid App Details")])
async def test_a_refusal_of_the_app_itself_is_account_level(monkeypatch, code, message):
    """contract §1.7: the key or the app is wrong — every later recipient would fail the same way (G-3)."""
    _fake(monkeypatch, lambda r: httpx.Response(code, json={"status": "error", "message": message}))
    assert await gt.send_template("9876543210", "t", []) == {
        "ok": False, "error": message, "status": code, "account": True}


async def test_the_source_number_is_stored_digits_only():
    """contract Delta 21: Gupshup wants "91…"; a "+91 88888 88888" pasted into Render must not fail every send."""
    from app.config import Settings
    assert Settings(GUPSHUP_TEMPLATE_SOURCE_NUMBER="+91 88888-88888").GUPSHUP_TEMPLATE_SOURCE_NUMBER == "918888888888"


async def test_submitted_is_gupshups_word_for_accepted(monkeypatch):
    """Gupshup's docs say "submitted" on one page and "success" on another (contract §1.6): the messageId decides."""
    _fake(monkeypatch, lambda r: httpx.Response(202, json={"status": "submitted", "messageId": "m2"}))
    assert await gt.send_template("9876543210", "t", []) == {"ok": True, "message_id": "m2", "status": 202}


@pytest.mark.parametrize("code", [429, 500, 503])
async def test_rate_limits_and_server_errors_are_retried_not_failed(monkeypatch, code):
    """Contract Delta 10."""
    _fake(monkeypatch, lambda r: httpx.Response(code, json={"message": "Too Many Requests", "status": "error"}))
    assert await gt.send_template("9876543210", "t", []) == {
        "ok": False, "error": "Too Many Requests", "status": code, "retry": True}


async def test_a_gateway_timeout_is_unknown_not_requeued(monkeypatch):
    """A 504: the request reached Gupshup's edge and the answer was lost — it may have been sent (G-12)."""
    _fake(monkeypatch, lambda r: httpx.Response(504, text="Gateway Timeout"))
    r = await gt.send_template("9876543210", "t", [])
    assert r["unknown"] is True and "retry" not in r and r["status"] == 504


async def test_a_2xx_without_a_message_id_is_unknown_not_failed(monkeypatch):
    """Gupshup may have taken it — failing the row would invite a retry that double-sends (G-12)."""
    _fake(monkeypatch, lambda r: httpx.Response(202, json={"status": "submitted"}))
    r = await gt.send_template("9876543210", "t", [])
    assert r["ok"] is False and r["unknown"] is True and r["status"] == 202


async def test_an_html_5xx_is_retried_with_truncated_text(monkeypatch):
    _fake(monkeypatch, lambda r: httpx.Response(502, text="<html>" + "x" * 1000))
    r = await gt.send_template("9876543210", "t", [])
    assert r["retry"] is True and len(r["error"]) <= 300


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
async def test_a_request_that_never_left_is_requeued(monkeypatch, exc):
    """No connection was made, so nothing reached Gupshup: back in the queue, and the loop backs off (G-2)."""
    def boom(req):
        raise exc("down", request=req)
    _fake(monkeypatch, boom)
    r = await gt.send_template("9876543210", "t", [])
    assert r["ok"] is False and r["retry"] is True and "unknown" not in r and r["status"] is None


@pytest.mark.parametrize("exc", [httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.WriteTimeout])
async def test_a_request_that_left_but_got_no_answer_is_unknown(monkeypatch, exc):
    def boom(req):
        raise exc("lost", request=req)
    _fake(monkeypatch, boom)
    r = await gt.send_template("9876543210", "t", [])
    assert r["ok"] is False and r["unknown"] is True and "retry" not in r


async def test_a_non_object_json_body_never_raises(monkeypatch):
    """send_template never raises for HTTP: a JSON list on a 2xx is just 'no messageId'."""
    _fake(monkeypatch, lambda r: httpx.Response(202, json=["weird"]))
    r = await gt.send_template("9876543210", "t", [])
    assert r["ok"] is False and r["unknown"] is True


async def test_unconfigured_raises_not_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "GUPSHUP_TEMPLATE_API_KEY", "")
    with pytest.raises(gt.NotConfigured, match="GUPSHUP_TEMPLATE_API_KEY"):
        await gt.send_template("9876543210", "t", [])
