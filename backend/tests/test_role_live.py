"""Role and active-state come off the users row, never off the JWT claim.

The token lives a week (JWT_EXPIRY_HOURS=168). If `current_user` trusted its
`role`, demoting an admin in Settings would leave them with real admin access
until it lapsed — `require_admin` and `_role_scope` both read that same value."""
import asyncio
import time

import jwt
import pytest
from fastapi import HTTPException

from app import config
from app.core import auth


def _token(role="admin", sub="11111111-1111-1111-1111-111111111111"):
    s = config.get_settings()
    return jwt.encode(
        {"sub": sub, "email": "someone@openhouse.in", "role": role, "iat": 0},
        s.JWT_SECRET, algorithm="HS256",
    )


class _Creds:
    def __init__(self, token):
        self.credentials = token


class _Req:
    """current_user takes the Request so it can read the local view-as header."""
    def __init__(self, who=None):
        self.headers = {"x-dev-user": who} if who else {}


class _FakeEngine:
    """Serves one users row, or raises to simulate a Neon blip."""

    def __init__(self, row, boom=False):
        self.row, self.boom, self.reads = row, boom, 0

    def connect(self):
        outer = self

        class _Ctx:
            async def __aenter__(self_):
                return self_

            async def __aexit__(self_, *exc):
                return False

            async def execute(self_, stmt, params=None):
                outer.reads += 1
                if outer.boom:
                    raise RuntimeError("connection reset")

                class _Res:
                    def first(self__):
                        return outer.row

                return _Res()

        return _Ctx()


@pytest.fixture(autouse=True)
def _live_auth(monkeypatch):
    """Auth on, no force-logout cutoff, and a clean per-user cache each test.

    The epoch cache is primed *fresh* so `_read_auth_epoch` short-circuits — it
    shares the same engine, and an unprimed one would spend a read of its own."""
    monkeypatch.setattr(config.get_settings(), "GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setattr(auth, "_epoch_cache", {"value": None, "read_at": time.monotonic()})
    auth._user_cache.clear()
    yield
    auth._user_cache.clear()


def _resolve(row, token_role="admin", boom=False):
    engine = _FakeEngine(row, boom=boom)
    import app.db

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(app.db, "neon_engine", lambda: engine)
        return asyncio.run(auth.current_user(_Req(), _Creds(_token(token_role)))), engine


def test_role_comes_from_the_row_not_the_token():
    """The whole point: token says admin, the row says rm, rm wins."""
    user, _ = _resolve(("rm", True), token_role="admin")
    assert user["role"] == "rm"
    with pytest.raises(HTTPException) as e:
        asyncio.run(auth.require_admin(user))
    assert e.value.status_code == 403


def test_promotion_lands_too():
    user, _ = _resolve(("admin", True), token_role="rm")
    assert user["role"] == "admin"


def test_deactivating_ends_the_session_now():
    with pytest.raises(HTTPException) as e:
        _resolve(("rm", False))
    assert e.value.status_code == 401


def test_the_row_is_cached_then_dropped_on_edit():
    """30s TTL keeps auth off the DB; forget_user makes an edit land immediately."""
    engine = _FakeEngine(("rm", True))
    import app.db

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(app.db, "neon_engine", lambda: engine)
        creds = _Creds(_token("admin"))
        asyncio.run(auth.current_user(_Req(), creds))
        asyncio.run(auth.current_user(_Req(), creds))
        assert engine.reads == 1, "second request inside the TTL must not re-read"

        auth.forget_user("11111111-1111-1111-1111-111111111111")
        asyncio.run(auth.current_user(_Req(), creds))
        assert engine.reads == 2, "an admin edit must invalidate the cache"


def test_a_db_blip_honours_the_token_rather_than_locking_everyone_out():
    """Fail-open, matching _read_auth_epoch. A Neon outage must not 403 the team."""
    user, _ = _resolve(None, token_role="admin", boom=True)
    assert user["role"] == "admin"


def test_an_unknown_id_falls_back_to_the_token():
    """Rows can vanish (deleted user); a malformed sub never reaches SQL."""
    user, engine = _resolve(None, token_role="rm")
    assert user["role"] == "rm"

    auth._user_cache.clear()
    assert asyncio.run(auth._read_user_state("not-a-uuid")) is None
