"""The /v1/acres router (admin only), the health check, the cron task and the TS mirror."""
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.auth import require_admin
from app.routers import acres
from app.services.acres_payload import OWNTYPE_IDS

ROOT = Path(__file__).resolve().parents[2]


def _load_cron_module():
    spec = importlib.util.spec_from_file_location("cron20", ROOT / "backend/scripts/20_cron_tasks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_acres_route_requires_admin():
    assert any(d.dependency is require_admin for d in acres.router.dependencies)
    paths = {(r.path, m) for r in acres.router.routes for m in r.methods}
    assert paths == {("/acres/listings", "GET"), ("/acres/check", "POST"), ("/acres/post", "POST"),
                     ("/acres/listings/{uid}", "PATCH"), ("/acres/health", "GET")}


def test_the_router_is_mounted():
    from app.main import app
    assert any(getattr(r, "path", "") == "/v1/acres/post" for r in app.routes)


def test_post_takes_at_most_five_and_check_at_most_300():
    with pytest.raises(ValidationError):
        acres.PostIn(items=[{"uid": f"U{i}"} for i in range(6)])
    acres.CheckIn(items=[{"uid": f"U{i}"} for i in range(300)])
    with pytest.raises(ValidationError):
        acres.CheckIn(items=[{"uid": f"U{i}"} for i in range(301)])


def test_prop_ids_are_normalised_and_checked():
    assert acres.MarkIn(status="live", prop_id=" p95503744 ").prop_id == "P95503744"
    with pytest.raises(ValidationError):
        acres.MarkIn(status="live", prop_id="95503744")
    with pytest.raises(ValidationError):
        acres.MarkIn(status="live")                       # live needs the id
    assert acres.MarkIn(status="removed").prop_id is None


def test_ownership_only_accepts_99acres_ids():
    for k in OWNTYPE_IDS:
        acres.Item(uid="U1", owntype=k)
    with pytest.raises(ValidationError):
        acres.Item(uid="U1", owntype="5")


async def test_health_reports_a_mismatch_and_never_the_token(monkeypatch):
    monkeypatch.setattr(acres.acres_client, "egress_ip", AsyncMock(return_value="206.189.139.59"))
    monkeypatch.setattr(acres.acres_client, "token", AsyncMock(return_value="eyJ.secret.sig"))
    monkeypatch.setattr(acres, "get_settings", lambda: SimpleNamespace(DROPLET_STATIC_IP="129.212.244.52"))
    out = await acres.health(login=True)
    assert out["egress_matches"] is False and out["login"] == {"ok": True, "error": None}
    assert "eyJ" not in json.dumps(out)


async def test_the_cron_task_fails_on_the_wrong_egress(monkeypatch):
    cron = _load_cron_module()
    from app.services import acres_client
    monkeypatch.setattr(acres_client, "egress_ip", AsyncMock(return_value="206.189.139.59"))
    monkeypatch.setattr(cron, "get_settings", lambda: SimpleNamespace(DROPLET_STATIC_IP="129.212.244.52"))
    with pytest.raises(RuntimeError, match="206.189.139.59"):
        await cron.task_acres_egress()


def test_the_cron_default_does_not_include_egress():
    cron = _load_cron_module()
    assert "acres_egress" in cron.TASKS and "acres_egress" not in cron.DEFAULT_TASKS


def test_the_modal_offers_exactly_the_99acres_ids():
    src = (ROOT / "frontend/src/features/acres/Acres.tsx").read_text()

    def ids(name):
        return re.findall(r'value:\s*"(\w+)"', re.search(rf"{name}\s*=\s*\[(.*?)\]", src, re.S).group(1))
    assert ids("OWNTYPE_OPTIONS") == list(OWNTYPE_IDS)


def test_the_modal_knows_the_not_attempted_marker():
    """The window keeps not-attempted rows Ready by matching this exact text."""
    from app.services.acres_listings import NOT_ATTEMPTED
    src = (ROOT / "frontend/src/features/acres/Acres.tsx").read_text()
    assert f'const NOT_ATTEMPTED = "{NOT_ATTEMPTED}"' in src
