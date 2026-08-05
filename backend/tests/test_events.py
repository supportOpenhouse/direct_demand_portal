"""The event bus behind Live Calls.

Redis is optional here exactly as it is in cache.py, so the in-process fan-out is
the path that runs in dev and on a single instance — these cover it directly. The
Redis path is a thin PUBLISH/SUBSCRIBE wrapper over the same interface.

The property that matters: a publish must never break the caller. Every publish
site is inside a call-lifecycle transition (place_bridge, the Bonvoice hangup, the
poller) where raising would strand a dialer slot on "Ringing…" for that RM.
"""
import asyncio

import pytest

from app.events import _subscribers, publish, pubsub_connect_kwargs, rm_channel, subscribe


@pytest.fixture(autouse=True)
def _empty_bus():
    """A leaked queue from one test would otherwise receive another test's publishes.

    conftest.py already forces the in-process path — without it these would assert
    against an empty queue while every publish went to the developer's real Redis.
    """
    _subscribers.clear()
    yield
    _subscribers.clear()


async def _drain(channel: str, count: int, timeout: float = 1.0) -> list[dict]:
    """Subscribe, collect `count` events, unsubscribe. Returns what arrived."""
    got: list[dict] = []
    agen = subscribe(channel)
    async for event in agen:
        got.append(event)
        if len(got) >= count:
            break
    await agen.aclose()
    return got


def test_the_subscriber_connection_has_no_read_timeout():
    """A subscriber's whole job is to sit idle waiting for an event, so it must not
    reuse cache.py's shared client — that one sets socket_timeout=2, which turns every
    quiet stretch into a read timeout. In production this killed the stream every two
    seconds: the log filled with 'redis SUBSCRIBE failed' and every RM silently ran on
    the polling fallback."""
    kwargs = pubsub_connect_kwargs()

    assert kwargs["socket_timeout"] is None
    # a half-open connection must still be noticed, just not on a 2s read deadline
    assert kwargs.get("health_check_interval")


def test_rm_channel_is_case_and_whitespace_insensitive():
    """The publisher reads rm_email off dial_queue; the subscriber reads it off the
    JWT. Those two disagree on case — `_dial_next` matches users with lower(email),
    and campaign `rms` are compared lowercased. If the channel key didn't normalise,
    an RM stored as 'A@x.com' would publish to a channel their own page never joins,
    and Live Calls would silently never update for them."""
    assert rm_channel("  Asha@X.com ") == rm_channel("asha@x.com")


def test_rm_channel_namespaces_its_keys():
    """Shares a Redis with the cache and the cron locks, which both use ddp:*."""
    assert rm_channel("a@x.com").startswith("ddp:")


async def test_a_subscriber_receives_a_published_event():
    ready = asyncio.Event()

    async def listener():
        agen = subscribe("rm:a@x.com")
        it = agen.__aiter__()
        ready.set()
        event = await it.__anext__()
        await agen.aclose()
        return event

    task = asyncio.create_task(listener())
    await asyncio.wait_for(ready.wait(), 1)
    await asyncio.sleep(0)  # let the generator register its queue before publishing
    await publish("rm:a@x.com", {"type": "call_started", "queue_item_id": "q1"})

    assert await asyncio.wait_for(task, 1) == {"type": "call_started", "queue_item_id": "q1"}


async def test_publish_with_no_subscriber_is_a_noop():
    """Nobody has Live Calls open — the dial must still go through."""
    await publish("rm:nobody@x.com", {"type": "call_ended"})
    assert _subscribers == {}


async def test_every_subscriber_on_a_channel_gets_the_event():
    """One RM with the page open in two tabs. Both must update."""
    a, b = asyncio.Queue(), asyncio.Queue()
    _subscribers.setdefault("rm:a@x.com", set()).update({a, b})

    await publish("rm:a@x.com", {"type": "call_ended"})

    assert a.get_nowait() == {"type": "call_ended"}
    assert b.get_nowait() == {"type": "call_ended"}


async def test_an_event_only_reaches_its_own_channel():
    """RM channels are per-email. One RM must never see another's calls."""
    mine, theirs = asyncio.Queue(), asyncio.Queue()
    _subscribers["rm:a@x.com"] = {mine}
    _subscribers["rm:b@x.com"] = {theirs}

    await publish("rm:a@x.com", {"type": "call_started"})

    assert mine.get_nowait() == {"type": "call_started"}
    assert theirs.empty()


async def test_closing_a_subscription_unregisters_its_queue():
    """Without this every page load leaks a queue that publish keeps writing to."""
    task = asyncio.create_task(_drain("rm:a@x.com", 1))
    await asyncio.sleep(0.01)  # let _drain register before we publish
    await publish("rm:a@x.com", {"type": "call_ended"})
    assert await asyncio.wait_for(task, 1) == [{"type": "call_ended"}]

    assert _subscribers.get("rm:a@x.com", set()) == set()


async def test_a_full_queue_drops_the_event_instead_of_blocking_publish():
    """A tab that stopped reading must not stall the dialer. The REST snapshot is
    the recovery path — a dropped nudge costs one refetch, a blocked publish costs
    the RM the rest of the campaign."""
    stalled = asyncio.Queue(maxsize=1)
    stalled.put_nowait({"type": "old"})
    _subscribers["rm:a@x.com"] = {stalled}

    await asyncio.wait_for(publish("rm:a@x.com", {"type": "call_ended"}), 1)

    assert stalled.get_nowait() == {"type": "old"}
    assert stalled.empty()
