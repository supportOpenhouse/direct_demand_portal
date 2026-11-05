"""The ONE 99acres client. Every call leaves through the droplet's Squid proxy, because
99acres answers only its Reserved IP (129.212.244.52) — anything else is HTTP 401.

Live behaviour (docs/99acres-api.md): errors are almost always HTTP 200 + `status: false`;
the token key is `accessToken` (camelCase); errorCode 10 = token rejected → re-login once,
retry once, never more. Never log or return a token.
"""
import asyncio
import time

import httpx

from ..config import get_settings

BASE = "https://www.99acres.com/99api"
SEGMENT = "qwerty"   # the doc's literal path segment; 99acres hasn't said it's anything else
_HEADERS = {"Content-Type": "application/json", "Accept": "application/json",
            "Accept-Encoding": "application/json"}


class AcresNotConfigured(Exception):
    pass


class AcresError(Exception):
    """99acres (or its edge) refused us; the message is shown to the admin as written."""


_cached: tuple[str, float] | None = None   # (token, valid-until epoch), one per process
_login_lock = asyncio.Lock()
# ponytail: one call at a time until 99acres publishes a rate limit.
_one_at_a_time = asyncio.Semaphore(1)


def _client() -> httpx.AsyncClient:
    s = get_settings()
    if not (s.ACRES_PROXY_URL and s.ACRES_USERNAME and s.ACRES_PASSWORD):
        raise AcresNotConfigured("99acres is not configured on this server")
    return httpx.AsyncClient(proxy=s.ACRES_PROXY_URL, trust_env=False, timeout=60.0)


async def _send(c: httpx.AsyncClient, method: str, url: str, **kw) -> httpx.Response:
    """Refusals that prove nothing was created become AcresError: the proxy unreachable (the
    request never left) and HTTP 401 (99acres refused our IP). A warm token skips login, so a
    lost egress shows up on the listing call, not at login."""
    try:
        r = await c.request(method, url, **kw)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ProxyError):
        raise AcresError("Couldn't reach 99acres through the proxy — nothing was sent")
    if r.status_code == 401:
        raise AcresError("99acres refused our IP — check the droplet's egress (STATUS.md)")
    return r


async def token(force: bool = False) -> str:
    global _cached
    async with _login_lock:
        if not force and _cached and _cached[1] > time.time():
            return _cached[0]
        s = get_settings()
        async with _client() as c:
            r = await _send(c, "POST", f"{BASE}/v21/accesstoken/{SEGMENT}?rtype=json", headers=_HEADERS,
                            json={"username": s.ACRES_USERNAME, "password": s.ACRES_PASSWORD})
        body = r.json()
        tok = body.get("accessToken") or body.get("accesstoken")
        if not body.get("status") or not tok:
            raise AcresError("99acres login refused — check 99ACRES_DASHBOARD_USERNAME / _PASSWORD")
        _cached = (tok, time.time() + int(body.get("expires") or 86400) - 300)
        return tok


async def call(method: str, path: str, body: dict | None = None) -> dict:
    """`path` like "v21/listing". Network errors, 5xx and non-JSON bodies propagate: the
    caller can't know whether 99acres acted, and must treat the outcome as unknown."""
    async with _one_at_a_time:
        for attempt in (1, 2):
            tok = await token(force=attempt == 2)
            async with _client() as c:
                r = await _send(c, method, f"{BASE}/{path}/{SEGMENT}?rtype=json", json=body,
                                headers={**_HEADERS, "Authorization": f"Bearer {tok}"})
            if r.status_code == 403 and "json" not in r.headers.get("content-type", ""):
                raise AcresError("Blocked by 99acres' firewall (Akamai 403) — nothing was created")
            r.raise_for_status()
            data = r.json()
            expired = (data.get("status") is False
                       and str((data.get("error") or {}).get("errorCode")) == "10")
            if not expired or attempt == 2:
                return data
    raise AssertionError("unreachable")


async def egress_ip() -> str:
    async with _client() as c:
        r = await c.get("https://ipv4.icanhazip.com/")
        r.raise_for_status()
        return r.text.strip()


def outcome_of(body: dict) -> tuple[str, dict]:
    """A listing call's answer → (status, fields to store)."""
    if body.get("status") is True:
        if body.get("prop_id"):
            return "live", {"prop_id": body["prop_id"], "quality_score": body.get("quality_score")}
        return "unknown", {"error": "99acres said yes but sent no listing id — check its dashboard"}
    if body.get("status") is not False:   # fail closed: only an explicit false created nothing
        return "unknown", {"error": "99acres answered in an unexpected shape — check its dashboard"}
    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    msg = err.get("errorMsg") or body.get("message") or "99acres refused the listing"
    detail = err.get("errorDetail") or body.get("errorDetail")
    if isinstance(detail, dict) and detail:
        msg += " — " + "; ".join(f"{k}: {v}" for k, v in detail.items())
    return ("duplicate" if str(err.get("errorCode")) == "5" else "failed"), {"error": msg}
