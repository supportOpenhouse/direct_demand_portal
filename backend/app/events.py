"""Fan-out for live call events, backing the Live Calls SSE stream.

In-process only: one asyncio.Queue per open SSE connection. That is correct because
the dialer, the Bonvoice webhook and the SSE endpoint all run in the ONE process with
RUN_SCHEDULER on. On an instance without the dialer nothing is published here, and the
page runs on its polling fallback.

Nothing downstream depends on delivery. Every publish site sits inside a call
transition (place_bridge, the Bonvoice hangup, the poller) where raising would
strand a dialer slot on "Ringing…" for the rest of the campaign, and the page's
REST snapshot re-reads the truth anyway. A dropped event costs one refetch.
"""
import asyncio
import logging
from collections.abc import AsyncIterator

# ponytail: single-process fan-out. If the dialer ever moves to its own worker, carry
# events over Postgres LISTEN/NOTIFY rather than reintroducing a broker.

log = logging.getLogger("events")

# channel -> queues, one per open SSE connection.
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
    for q in list(_subscribers.get(channel, ())):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # The snapshot refetch is the recovery path; blocking here would stall
            # whichever call transition is publishing.
            log.warning("events: subscriber queue full on %s — event dropped", channel)


async def subscribe(channel: str) -> AsyncIterator[dict]:
    """Yield events on `channel` until the consumer stops iterating or closes it."""
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
