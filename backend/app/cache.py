"""Optional managed-Redis layer: shared cache, JSON helpers, and a distributed lock.

Lazy singleton like db.py — the client is created on first use, never at import,
and `get_redis()` returns None when REDIS_URL is unset so the app still boots and
behaves exactly as before with no Redis. Every helper SWALLOWS Redis errors: a
Redis outage degrades to a cache miss / "run anyway", never a failed request.
"""
import asyncio
import json
import logging
from uuid import uuid4

from .config import get_settings

log = logging.getLogger("cache")

_redis = None  # redis.asyncio.Redis | None
_initialized = False  # distinguishes "not created yet" from "created but unavailable"


def get_redis():
    """The shared async Redis client, or None when REDIS_URL is unset/unavailable."""
    global _redis, _initialized
    settings = get_settings()
    if not settings.redis_configured:
        return None
    if not _initialized:
        _initialized = True
        try:
            import redis.asyncio as aioredis  # function-local: dep not needed when unconfigured

            _redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
                max_connections=10,
            )
        except Exception:  # noqa: BLE001 — a bad URL/import must never crash boot
            log.exception("could not init Redis — falling back to in-memory")
            _redis = None
    return _redis


def _swallow():
    """Exception tuple to catch around every Redis call (incl. when redis isn't importable)."""
    excs = [OSError, asyncio.TimeoutError]
    try:
        from redis.exceptions import RedisError

        excs.append(RedisError)
    except Exception:  # noqa: BLE001
        pass
    return tuple(excs)


async def cache_get_json(key: str):
    """Parsed JSON at `key`, or None on miss / any Redis error."""
    r = get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except _swallow():
        log.warning("redis GET %s failed — treating as miss", key)
        return None
    except (json.JSONDecodeError, TypeError):
        return None


async def cache_set_json(key: str, value, ttl: int) -> None:
    """Store `value` as JSON with a TTL. Best-effort; errors are swallowed."""
    r = get_redis()
    if r is None:
        return
    try:
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except _swallow():
        log.warning("redis SET %s failed — skipping", key)


async def cache_delete(*keys: str) -> None:
    """Delete keys (e.g. to invalidate across instances). Best-effort."""
    r = get_redis()
    if r is None or not keys:
        return
    try:
        await r.delete(*keys)
    except _swallow():
        log.warning("redis DEL %s failed — skipping", keys)


async def try_acquire_lock(name: str, ttl: int) -> str | None:
    """Distributed lock via SET NX EX. Returns a token if acquired, None if held
    elsewhere. With no Redis OR on a Redis error, returns a 'local' sentinel so the
    caller RUNS ANYWAY (fail-open: a transient Redis blip must not halt cron jobs;
    both syncs are idempotent)."""
    r = get_redis()
    if r is None:
        return "local"
    token = uuid4().hex
    try:
        ok = await r.set(f"ddp:lock:{name}", token, nx=True, ex=ttl)
        return token if ok else None
    except _swallow():
        log.warning("redis lock %s failed — running anyway (fail-open)", name)
        return "local"


async def redis_ping() -> str:
    """'ok' | 'error' | 'not_configured' — for the health endpoint."""
    r = get_redis()
    if r is None:
        return "not_configured"
    try:
        await r.ping()
        return "ok"
    except _swallow():
        return "error"


async def close_redis() -> None:
    global _redis, _initialized
    if _redis is not None:
        try:
            await _redis.aclose()
        except _swallow():
            pass
        _redis = None
    _initialized = False
