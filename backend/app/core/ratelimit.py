"""Rate limiting via slowapi.

Deliberately uses an IN-MEMORY store (not Redis): the limiter runs on the login
path, and a Redis hiccup with the default slowapi config raised → a 500 on sign-in
(it happened in prod). In-memory means the limiter makes NO network call, so it can
never take down a request. Limits are therefore per-instance — perfectly fine for
this single-instance internal tool. (Redis is still used for the match cache + cron
lock, which are already fail-soft.) `swallow_errors=True` is belt-and-suspenders in
case a Redis store is ever wired in here later.

There is no global `default_limits` — only explicitly-decorated routes are limited
(so the debounced live-match preview is never throttled). Today only /auth/google.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address


def _client_ip(request) -> str:
    """Real client IP behind Render/Vercel's proxy: first hop of X-Forwarded-For,
    falling back to the socket address."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(
    key_func=_client_ip,
    storage_uri="memory://",
    swallow_errors=True,
    headers_enabled=True,
)
