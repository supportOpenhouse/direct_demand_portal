"""Shared test setup.

Settings load the developer's real ../.env, which on a working machine has REDIS_URL
filled in. Without this every test that reaches a publish or a cache helper would open
a socket to the live Redis — slow, flaky offline, and it would let one developer's
running app see events emitted by another's test run.

Forcing the in-process path is also the honest default: it is what a single instance
and every dev machine actually run, and the Redis path is a thin PUBLISH/SUBSCRIBE
wrapper over the same interface.
"""
import pytest


@pytest.fixture(autouse=True)
def _no_redis_in_tests(monkeypatch):
    # cache.py and events.py each hold their own reference to get_redis, so patching
    # the definition alone would leave events.py still talking to a real server.
    monkeypatch.setattr("app.cache.get_redis", lambda: None)
    monkeypatch.setattr("app.events.get_redis", lambda: None)
    # Subscribers open a connection of their own — a subscriber must not inherit the
    # shared client's 2s read timeout — so it needs neutralising separately.
    monkeypatch.setattr("app.events._pubsub_client", lambda: None)
