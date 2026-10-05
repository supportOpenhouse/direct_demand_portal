"""External studio-video endpoint: the key gate runs before any database access, so
these need no engine (and must never reach one — backend/.env is PROD)."""
import pytest
from fastapi import HTTPException

from app import config
from app.routers import studio_external as mod


async def _status(monkeypatch, secret: str, sent: str | None) -> int:
    monkeypatch.setattr(config.get_settings(), "CRM_API_KEY", secret)
    # if the gate ever lets a bad key through, this makes the test fail loudly instead
    # of querying the real studio DB
    monkeypatch.setattr(mod, "studio_engine", lambda: pytest.fail("reached the database"))
    with pytest.raises(HTTPException) as e:
        await mod.studio_videos("12", x_crm_key=sent)
    return e.value.status_code


async def test_unset_key_refuses_everyone(monkeypatch):
    """Fail closed — dev included. No key configured is never an open endpoint."""
    assert await _status(monkeypatch, "", None) == 503
    assert await _status(monkeypatch, "", "") == 503


async def test_wrong_or_missing_key_is_401(monkeypatch):
    assert await _status(monkeypatch, "k3y", None) == 401
    assert await _status(monkeypatch, "k3y", "nope") == 401


def test_the_query_tells_unknown_homes_from_unstitched_ones():
    sql = str(mod.VIDEOS_BY_HOME)
    assert "LEFT JOIN onboarded_properties_videos v ON v.property_uid = p.uid" in sql
    assert "WHERE p.core_home_id = ANY(:homes)" in sql
    assert "p.app_listed_videos" in sql, "the app-listed video is the fallback"
    assert "DISTINCT ON (p.core_home_id)" in sql, "one answer per home, even when two properties share it"


def test_the_id_list_is_parsed_strictly():
    assert mod._parse_ids("12,630,12") == [12, 630]          # de-duped, request order kept
    assert mod._parse_ids(" 12 , 630 ,") == [12, 630]       # spaces / trailing comma tolerated
    for bad in ("", ",", "12,abc", "12;630", "1.5"):
        with pytest.raises(HTTPException) as e:
            mod._parse_ids(bad)
        assert e.value.status_code == 422, bad
    with pytest.raises(HTTPException):
        mod._parse_ids(",".join(str(i) for i in range(mod.MAX_IDS + 1)))


async def test_each_id_gets_its_own_status(monkeypatch):
    """ok (stitched, or the app-listed fallback) / not_stitched / not_found, in the order
    asked — no DB: a fake engine answers."""
    from datetime import datetime, timezone

    rows = [
        {"core_home_id": 12, "uid": "A", "stitched_url": "https://v/12.mp4",
         "stitched_at": datetime(2026, 8, 31, tzinfo=timezone.utc), "app_listed_videos": "https://app/12.mp4"},
        {"core_home_id": 630, "uid": "B", "stitched_url": None, "stitched_at": None, "app_listed_videos": None},
        {"core_home_id": 77, "uid": "C", "stitched_url": None, "stitched_at": None,
         "app_listed_videos": "https://app/77.mp4"},
    ]

    class _Res:
        def mappings(self):
            return rows

    class _Conn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, _sql, params):
            assert params == {"homes": [630, 999, 12, 77]}
            return _Res()

    class _Engine:
        def connect(self):
            return _Conn()

    monkeypatch.setattr(config.get_settings(), "CRM_API_KEY", "k3y")
    monkeypatch.setattr(mod, "studio_engine", lambda: _Engine())
    out = (await mod.studio_videos("630,999,12,77", x_crm_key="k3y"))["items"]
    assert [(i["core_home_id"], i["status"], i["source"]) for i in out] == [
        (630, "not_stitched", None), (999, "not_found", None), (12, "ok", "stitched"), (77, "ok", "app_listed")]
    # stitched wins over the app-listed video when a home has both
    assert out[2]["stitched_url"] == "https://v/12.mp4" and out[2]["stitched_at"].startswith("2026-08-31")
    assert out[3]["stitched_url"] == "https://app/77.mp4" and out[3]["stitched_at"] is None
    assert out[0]["stitched_url"] is None and out[0]["uid"] == "B"


def test_the_route_is_mounted_without_jwt():
    """It's for another app's server — `current_user` would demand a portal login."""
    from app.main import app
    route = next(r for r in app.routes if getattr(r, "path", "") == "/v1/external/studio-video/{core_home_ids}")
    assert "current_user" not in str(route.dependant.dependencies)
