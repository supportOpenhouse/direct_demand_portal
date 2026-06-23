"""Rate limiting via slowapi. Backed by Redis when REDIS_URL is set (shared across
instances), else an in-process memory store (works in dev/tests/single instance)."""
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..config import get_settings


def _client_ip(request) -> str:
    """Real client IP behind Render/Vercel's proxy: first hop of X-Forwarded-For,
    falling back to the socket address."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return get_remote_address(request)


_settings = get_settings()
limiter = Limiter(
    key_func=_client_ip,
    storage_uri=_settings.REDIS_URL or "memory://",
    default_limits=["120/minute"],
    headers_enabled=True,
)
