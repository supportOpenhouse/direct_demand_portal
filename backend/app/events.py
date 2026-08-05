"""Fan-out for live call events, backing the Live Calls SSE stream.

Same shape as cache.py: Redis when REDIS_URL is set, a working fallback when it
isn't, and every error swallowed. The fallback matters more here than it does for
the cache — `render.yaml` documents running the scheduler as a separate Background
Worker, and in that topology the process that flips a dial_queue row is NOT the one
holding the RM's SSE connection. Redis is what carries the event across; the
in-process path is correct only on a single instance.

Nothing downstream depends on delivery. Every publish site sits inside a call
transition (place_bridge, the Bonvoice hangup, the poller) where raising would
strand a dialer slot on "Ringing…" for the rest of the campaign, and the page's
REST snapshot re-reads the truth anyway. A dropped event costs one refetch.
"""
import asyncio
import json
import logging
from collections.abc import AsyncIterator

from .cache import _swallow, get_redis

log = logging.getLogger("events")

# channel -> queues, one per open SSE connection. Only used when Redis is absent.
_subscribers: dict[str, set[asyncio.Queue]] = {}

# Deep enough that a briefly busy tab keeps its events, shallow enough that a tab
# which stopped reading is dropped rather than grown unboundedly.
_QUEUE_MAX = 32


def rm_channel(email: str) -> str:
    """The per-RM channel.

    Normalised because the two ends disagree on case: the publisher reads rm_email
    off dial_queue, the subscriber reads it off the JWT, and `_dial_next` matches
    users with lower(email). Without this an RM stored as 'A@x.com' would publish to
    a channel their own page never joins.
    """
    return f"ddp:rm:{(email or '').strip().lower()}"


async def publish(channel: str, payload: dict) -> None:
    """Best-effort fan-out. Never raises."""
    r = get_redis()
    if r is not None:
        try:
            await r.publish(channel, json.dumps(payload, default=str))
            return
        except _swallow():
            log.warning("redis PUBLISH %s failed — event dropped", channel)
            return

    for q in list(_subscribers.get(channel, ())):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # The snapshot refetch is the recovery path; blocking here would stall
            # whichever call transition is publishing.
            log.warning("events: subscriber queue full on %s — event dropped", channel)


async def subscribe(channel: str) -> AsyncIterator[dict]:
    """Yield events on `channel` until the consumer stops iterating or closes it."""
    r = get_redis()
    if r is not None:
        pubsub = r.pubsub()
        try:
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    yield json.loads(message["data"])
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
        except _swallow():
            log.warning("redis SUBSCRIBE %s failed — stream ends, client falls back", channel)
        finally:
            try:
                await pubsub.aclose()
            except Exception:  # noqa: BLE001 — teardown must not mask the real exit
                pass
        return

    q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    _subscribers.setdefault(channel, set()).add(q)
    try:
        while True:
            yield await q.get()
    finally:
        subs = _subscribers.get(channel)
        if subs is not None:
            subs.discard(q)
            if not subs:
                _subscribers.pop(channel, None)
