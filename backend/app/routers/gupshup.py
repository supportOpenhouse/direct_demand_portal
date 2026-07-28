"""Gupshup WhatsApp callback endpoint — plumbing only.

Gupshup POSTs everything (inbound messages, delivery events, opt-ins, billing) to a
single callback URL. This phase receives it, checks the optional shared secret, and
keeps the last N payloads in memory so the real shapes can be read off
GET /v1/gupshup/recent before anything is modelled. No table, no lead matching, no
outbound send yet.

Hard requirement: answer 2xx, fast. Gupshup retries a failing callback and eventually
disables the URL, so every failure path below is swallowed into a 200 — except a bad
shared secret, which isn't Gupshup calling in the first place.
"""
import json
import logging
import secrets
from collections import deque
from datetime import datetime, timezone
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..config import get_settings
from ..core.auth import require_admin

log = logging.getLogger("gupshup")
router = APIRouter(tags=["gupshup"])

# ponytail: in-memory ring, not a table — its whole job is to reveal payload shapes,
# and losing it on restart costs nothing. Model it properly once the shapes are known.
_RECENT: deque[dict] = deque(maxlen=50)


def parse_body(raw: bytes, content_type: str) -> dict | list | str:
    """Gupshup sends JSON on the WhatsApp callback and form-encoded on some of the
    older ones. Return whichever parses; fall back to the raw text so an unexpected
    format still shows up in /recent instead of vanishing."""
    body = raw.decode("utf-8", "replace")
    if not body:
        return {}
    if "form-urlencoded" in content_type:
        return dict(parse_qsl(body))
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def _check_token(request: Request) -> None:
    """Optional shared secret via ?token= — Gupshup's dashboard only accepts a URL,
    so a query param is the only channel available. Unset = open (dev)."""
    secret = get_settings().GUPSHUP_WEBHOOK_SECRET.strip()
    if secret and not secrets.compare_digest(request.query_params.get("token", ""), secret):
        raise HTTPException(status_code=403, detail="invalid token")


@router.get("/gupshup/webhook")
async def gupshup_verify(request: Request):
    """Smoke-test / verification hit — Gupshup and browsers both GET the URL first."""
    _check_token(request)
    return {"status": "ok"}


@router.post("/gupshup/webhook", status_code=200, response_class=Response)
async def gupshup_webhook(request: Request):
    """Gupshup wants 2xx with an EMPTY body inside 10s (<500ms recommended), or it
    retries and eventually disables the callback. Everything here is O(1)."""
    _check_token(request)
    try:
        body = parse_body(await request.body(), request.headers.get("content-type", ""))
    except Exception:  # noqa: BLE001 — a 500 here makes Gupshup disable the callback
        log.exception("gupshup: unreadable callback body")
        return Response(status_code=200)

    entry = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "type": body.get("type") if isinstance(body, dict) else None,
        "body": body,
    }
    _RECENT.appendleft(entry)
    log.info("gupshup callback type=%s body=%s", entry["type"], json.dumps(body, default=str)[:2000])
    return Response(status_code=200)


@router.get("/gupshup/recent", dependencies=[Depends(require_admin)])
async def gupshup_recent():
    """The last 50 callbacks, newest first — for reading real payload shapes."""
    return {"count": len(_RECENT), "items": list(_RECENT)}
