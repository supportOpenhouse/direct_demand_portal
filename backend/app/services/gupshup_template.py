"""The one call to Gupshup's template API, from the TEMPLATE app (spec §2.1, §5.2).
One recipient per call — that is the API's shape — and the messageId it returns is what
ties every receipt and button answer back to a campaign recipient."""
import json
import logging

import httpx

from ..config import get_settings

log = logging.getLogger("gupshup_template")
TEMPLATE_PATH = "/wa/api/v1/template/msg"

# The request never left this machine: no connection was made (refused, DNS, TLS) or none was free in the pool.
# Nothing can have reached Gupshup, so the row goes back in the queue — unlike a read timeout or a dropped
# response, where Gupshup may have taken the message and resending could message the person twice.
NEVER_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


class NotConfigured(RuntimeError):
    pass


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="https://api.gupshup.io", timeout=20.0)


def _account_level(status: int, error: str) -> bool:
    """A refusal of the APP, not of this one recipient: every later send would fail the same way, so the
    campaign must stop instead of failing the list one row at a time (contract §1.7). 401/403 = the key; a 400
    is per-recipient only when it is about the destination ("Invalid Destination") — anything else, e.g.
    "Invalid App Details", is the app's own configuration."""
    return status in (401, 403) or (status == 400 and "destination" not in error.lower())


async def send_template(phone10: str, gupshup_template_id: str, params: list[str]) -> dict:
    """{"ok": True, "message_id", "status"} when Gupshup took it. Otherwise {"ok": False, "error", "status"} plus
    at most one of: "retry" (refused, nothing sent — requeue), "unknown" (it may have been sent — leave it
    'submitted'), "account" (the app itself was refused — pause the campaign). `status` is the HTTP status,
    None when no response came back. Never raises for HTTP."""
    s = get_settings()
    if not s.gupshup_template_configured:
        raise NotConfigured(", ".join(s.gupshup_template_missing))
    form = {
        "channel": "whatsapp",
        "source": s.GUPSHUP_TEMPLATE_SOURCE_NUMBER,
        "destination": "91" + phone10,
        "src.name": s.GUPSHUP_TEMPLATE_APP_NAME,
        "template": json.dumps({"id": gupshup_template_id, "params": [str(p) for p in params]}),
    }
    try:
        async with _client() as c:
            r = await c.post(TEMPLATE_PATH, data=form, headers={"apikey": s.GUPSHUP_TEMPLATE_API_KEY})
    except NEVER_SENT as e:
        log.warning("gupshup template send: couldn't connect (…%s): %s", phone10[-4:], e)
        return {"ok": False, "error": f"couldn't reach Gupshup: {e}", "status": None, "retry": True}
    except httpx.HTTPError as e:
        # the request went out and no answer came back: it may or may not have reached Gupshup,
        # so the row stays 'submitted' ("Unknown — check")
        log.warning("gupshup template send: no answer (…%s): %s", phone10[-4:], e)
        return {"ok": False, "error": f"no answer from Gupshup: {e}", "status": None, "unknown": True}
    try:
        body = r.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):  # never raise for HTTP: a JSON list/string is just "no messageId"
        body = {}
    code = r.status_code
    # A messageId on a 2xx = ACCEPTED by Gupshup (status "submitted" or "success" — the word varies,
    # contract §1.6); delivery and most per-recipient failures arrive later as callbacks. A 2xx can
    # still carry {"status":"error"} — the status field decides, not the code.
    if code < 300 and body.get("status") != "error" and body.get("messageId"):
        return {"ok": True, "message_id": str(body["messageId"]), "status": code}
    error = str(body.get("message") or r.text[:300] or f"HTTP {code}")[:300]
    if code < 300 and body.get("status") != "error":
        # a 2xx with no messageId and no error: Gupshup may well have taken it, we just can't tell
        log.warning("gupshup template send: 2xx without a messageId (…%s): %s", phone10[-4:], error)
        return {"ok": False, "error": error, "status": code, "unknown": True}
    if code == 504:
        # a gateway timeout: the request reached Gupshup's edge and the answer was lost — it may have been sent
        log.warning("gupshup template send: 504 (…%s): %s", phone10[-4:], error)
        return {"ok": False, "error": error, "status": code, "unknown": True}
    if code == 429 or code >= 500:
        log.warning("gupshup template send refused (%s) for …%s: %s", code, phone10[-4:], error)
        return {"ok": False, "error": error, "status": code, "retry": True}  # refused, nothing sent (contract Delta 10)
    if _account_level(code, error):
        log.error("gupshup template send: the template app was refused (%s): %s", code, error)
        return {"ok": False, "error": error, "status": code, "account": True}
    return {"ok": False, "error": error, "status": code}
