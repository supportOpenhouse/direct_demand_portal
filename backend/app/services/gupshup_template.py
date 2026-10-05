"""The one call to Gupshup's template API, from the TEMPLATE app (spec §2.1, §5.2).
One recipient per call — that is the API's shape — and the messageId it returns is what
ties every receipt and button answer back to a campaign recipient."""
import json
import logging

import httpx

from ..config import get_settings

log = logging.getLogger("gupshup_template")
TEMPLATE_PATH = "/wa/api/v1/template/msg"


class NotConfigured(RuntimeError):
    pass


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="https://api.gupshup.io", timeout=20.0)


async def send_template(phone10: str, gupshup_template_id: str, params: list[str]) -> dict:
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
    except httpx.HTTPError as e:
        # may or may not have reached Gupshup: the row stays 'submitted' ("Unknown — check")
        log.warning("gupshup template send: no answer (…%s): %s", phone10[-4:], e)
        return {"ok": False, "error": f"couldn't reach Gupshup: {e}", "unknown": True}
    try:
        body = r.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):  # never raise for HTTP: a JSON list/string is just "no messageId"
        body = {}
    # A messageId on a 2xx = ACCEPTED by Gupshup (status "submitted" or "success" — the word varies,
    # contract §1.6); delivery and most per-recipient failures arrive later as callbacks. A 2xx can
    # still carry {"status":"error"} — the status field decides, not the code.
    if r.status_code < 300 and body.get("status") != "error" and body.get("messageId"):
        return {"ok": True, "message_id": str(body["messageId"])}
    error = str(body.get("message") or r.text[:300] or f"HTTP {r.status_code}")[:300]
    if r.status_code == 429 or r.status_code >= 500:
        log.warning("gupshup template send refused (%s) for …%s: %s", r.status_code, phone10[-4:], error)
        return {"ok": False, "error": error, "retry": True}  # refused, nothing sent (contract Delta 10)
    return {"ok": False, "error": error}
