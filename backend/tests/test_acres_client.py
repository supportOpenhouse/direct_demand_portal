"""The 99acres client — against a fake 99acres (httpx.MockTransport): no network, no DB."""
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.models import AcresListing
from app.services import acres_client

LOGIN_OK = {"status": True, "accessToken": "eyJ.a.b", "expires": 86400}


def _fake_99(monkeypatch, handler):
    """Point the client at `handler`, with a cold token cache and fake credentials."""
    seen: list[httpx.Request] = []

    def transport(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    monkeypatch.setattr(acres_client, "get_settings", lambda: SimpleNamespace(
        DROPLET_STATIC_IP="129.212.244.52", DROPLET_SQUID_PORT="31847", DROPLET_SQUID_USERNAME="acres", DROPLET_SQUID_PASSWORD="pw", ACRES_DASHBOARD_USERNAME="u", ACRES_DASHBOARD_PASSWORD="pw"))
    monkeypatch.setattr(acres_client, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    monkeypatch.setattr(acres_client, "_cached", None)
    return seen


def _fake_99_after_login(monkeypatch, resp: httpx.Response):
    return _fake_99(monkeypatch, lambda r: httpx.Response(200, json=LOGIN_OK) if "accesstoken" in r.url.path else resp)


async def test_login_reads_the_camelcase_key_and_sends_creds_in_the_body(monkeypatch):
    seen = _fake_99(monkeypatch, lambda r: httpx.Response(200, json=LOGIN_OK))
    assert await acres_client.token() == "eyJ.a.b"
    assert seen[0].url.path.endswith("/v21/accesstoken/qwerty") and json.loads(seen[0].content) == {"username": "u", "password": "pw"}
    assert await acres_client.token() == "eyJ.a.b" and len(seen) == 1          # cached


async def test_a_refused_login_and_a_wrong_ip_are_errors_not_tokens(monkeypatch):
    _fake_99(monkeypatch, lambda r: httpx.Response(200, json={"status": False, "message": None}))
    with pytest.raises(acres_client.AcresError, match="login refused"):
        await acres_client.token()
    _fake_99(monkeypatch, lambda r: httpx.Response(401, json={"message": "Unauthorized Client"}))
    with pytest.raises(acres_client.AcresError, match="refused our IP"):
        await acres_client.token(force=True)


async def test_error_10_relogs_in_once_and_retries_once(monkeypatch):        # Review Focus 4
    def handler(r):
        if "accesstoken" in r.url.path:
            return httpx.Response(200, json=LOGIN_OK)
        return httpx.Response(200, json={"status": False, "error": {"errorCode": "10", "errorMsg": "INAVLID KEY"}})
    seen = _fake_99(monkeypatch, handler)
    body = await acres_client.call("POST", "v21/listing", {"x": "1"})
    assert ["accesstoken" in r.url.path for r in seen] == [True, False, True, False]   # no third listing call
    assert body["error"]["errorCode"] == "10"


async def test_calls_carry_the_bearer_and_the_doc_url_shape(monkeypatch):
    seen = _fake_99_after_login(monkeypatch, httpx.Response(200, json={"status": True, "prop_id": "E1"}))
    await acres_client.call("POST", "v21/listing", {"x": "1"})
    listing = seen[-1]
    assert str(listing.url) == "https://www.99acres.com/99api/v21/listing/qwerty?rtype=json"
    assert listing.headers["authorization"] == "Bearer eyJ.a.b" and json.loads(listing.content) == {"x": "1"}


async def test_listing_answers_map_to_statuses(monkeypatch):                # Review Focus 3
    assert acres_client.outcome_of({"status": True, "prop_id": "E95607134", "quality_score": 75}) == ("live", {"prop_id": "E95607134", "quality_score": 75})
    assert acres_client.outcome_of({"status": True})[0] == "unknown"          # said yes, named nothing: it may exist
    assert acres_client.outcome_of({"status": False, "error": {"errorCode": "5", "errorMsg": "duplicate property: similar to E1"}})[0] == "duplicate"
    st, d = acres_client.outcome_of({"status": False, "error": {"errorCode": "6", "errorMsg": "Error while saving the form", "errorDetail": {"Locality": "required"}}})
    assert st == "failed" and "Locality: required" in d["error"]
    for resp in (httpx.Response(502, text="<html>bad gateway</html>"), httpx.Response(200, text="<html>")):
        _fake_99_after_login(monkeypatch, resp)
        with pytest.raises((httpx.HTTPError, ValueError)):
            await acres_client.call("POST", "v21/listing", {"x": "1"})
    _fake_99_after_login(monkeypatch, httpx.Response(403, text="<HTML>Access Denied</HTML>"))
    with pytest.raises(acres_client.AcresError, match="Akamai 403"):
        await acres_client.call("POST", "v21/listing", {"x": "1"})


async def test_egress_is_the_ip_echo_through_the_proxy(monkeypatch):
    seen = _fake_99(monkeypatch, lambda r: httpx.Response(200, text="129.212.244.52\n"))
    assert await acres_client.egress_ip() == "129.212.244.52"
    assert seen[0].url.host == "ipv4.icanhazip.com"


def test_no_proxy_means_not_configured(monkeypatch):
    monkeypatch.setattr(acres_client, "get_settings", lambda: SimpleNamespace(
        DROPLET_STATIC_IP="", DROPLET_SQUID_PORT="", DROPLET_SQUID_USERNAME="", DROPLET_SQUID_PASSWORD="",
        ACRES_DASHBOARD_USERNAME="u", ACRES_DASHBOARD_PASSWORD="p"))
    with pytest.raises(acres_client.AcresNotConfigured):
        acres_client._client()


def test_the_proxy_url_is_built_from_the_droplet_settings():
    """The four DROPLET_* keys already in backend/.env ARE the proxy; user + password are
    URL-quoted so a password with @ : / can't break the URL."""
    s = SimpleNamespace(DROPLET_STATIC_IP="129.212.244.52", DROPLET_SQUID_PORT="31847",
                        DROPLET_SQUID_USERNAME="acres", DROPLET_SQUID_PASSWORD="p@ss:w/rd")
    assert acres_client.proxy_url(s) == "http://acres:p%40ss%3Aw%2Frd@129.212.244.52:31847"


def test_only_the_client_sets_a_proxy():
    src = {p.name: p.read_text() for p in Path(acres_client.__file__).parents[1].rglob("*.py")}
    assert [n for n, s in src.items() if "proxy=" in s] == ["acres_client.py"]
    assert "trust_env=False" in src["acres_client.py"]


def test_credentials_come_from_the_existing_env_keys(monkeypatch):
    monkeypatch.setenv("ACRES_DASHBOARD_USERNAME", "user")
    monkeypatch.setenv("ACRES_DASHBOARD_PASSWORD", "pw")
    for k, v in {"DROPLET_STATIC_IP": "129.212.244.52", "DROPLET_SQUID_PORT": "31847",
                 "DROPLET_SQUID_USERNAME": "acres", "DROPLET_SQUID_PASSWORD": "sq"}.items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)
    assert (s.ACRES_DASHBOARD_USERNAME, s.ACRES_DASHBOARD_PASSWORD) == ("user", "pw")
    assert acres_client.proxy_url(s) == "http://acres:sq@129.212.244.52:31847"


def test_the_model_guards_repeats():
    t = AcresListing.__table__
    assert [c.name for c in t.primary_key] == ["uid"] and t.c.prop_id.unique and not t.c.status.nullable


def test_an_unexpected_answer_shape_fails_closed():
    """Only an explicit status:false is 'failed' (postable again); anything else may be a listing."""
    assert acres_client.outcome_of({"foo": 1})[0] == "unknown"
    assert acres_client.outcome_of({"status": "true", "prop_id": "E1"})[0] == "unknown"


async def test_a_listing_call_401_is_a_refusal_not_an_unknown(monkeypatch):
    """A warm token skips login, so a lost egress shows up HERE as 401 — nothing was created."""
    _fake_99_after_login(monkeypatch, httpx.Response(401, json={"message": "Unauthorized Client"}))
    with pytest.raises(acres_client.AcresError, match="refused our IP"):
        await acres_client.call("POST", "v21/listing", {"x": "1"})


async def test_a_proxy_that_cannot_connect_is_a_refusal(monkeypatch):
    """The request never left: nothing can have been created on 99acres."""
    def boom(r):
        raise httpx.ConnectError("proxy down")
    _fake_99(monkeypatch, boom)
    with pytest.raises(acres_client.AcresError, match="proxy"):
        await acres_client.token()


def test_not_configured_names_the_missing_settings(monkeypatch):
    """A bare "not configured" 503 can't tell a missing proxy from a missing login — and on
    Render nobody can run a debugger. Name the env keys (never their values)."""
    monkeypatch.setattr(acres_client, "get_settings", lambda: SimpleNamespace(
        DROPLET_STATIC_IP="129.212.244.52", DROPLET_SQUID_PORT="31847", DROPLET_SQUID_USERNAME="acres",
        DROPLET_SQUID_PASSWORD="", ACRES_DASHBOARD_USERNAME="u", ACRES_DASHBOARD_PASSWORD="p"))
    with pytest.raises(acres_client.AcresNotConfigured, match=r"set DROPLET_SQUID_PASSWORD$"):
        acres_client._client()
    monkeypatch.setattr(acres_client, "get_settings", lambda: SimpleNamespace(
        DROPLET_STATIC_IP="129.212.244.52", DROPLET_SQUID_PORT="31847", DROPLET_SQUID_USERNAME="acres", DROPLET_SQUID_PASSWORD="pw", ACRES_DASHBOARD_USERNAME="", ACRES_DASHBOARD_PASSWORD=""))
    with pytest.raises(acres_client.AcresNotConfigured, match=r"ACRES_DASHBOARD_USERNAME, ACRES_DASHBOARD_PASSWORD"):
        acres_client._client()
