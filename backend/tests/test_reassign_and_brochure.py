"""Change RM on a visit + home brochures — the two Core endpoints shipped 24 Sep.

The service calls run against a fake Core (httpx.MockTransport): no network, no DB.
The router rules are asserted on source, like test_manage_visits.py.
"""
import inspect
import json

import httpx

from app.routers import demand_dashboard as dd_router
from app.routers import visits as visits_router
from app.services import crm_booking


def _fake_core(monkeypatch, handler):
    """Point crm_booking's Core client at `handler`, keeping the real key header."""
    seen: list[httpx.Request] = []

    def transport(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    monkeypatch.setattr(crm_booking, "_client", lambda: httpx.AsyncClient(
        base_url="https://core.test/api/v1/oh/", headers={"X-CRM-Key": "k"},
        transport=httpx.MockTransport(transport)))
    return seen


# --- reassign -------------------------------------------------------------------------

async def test_reassign_sends_ONLY_sales_manager(monkeypatch):
    """A partial update: anything else in the body is something Core would rewrite. The
    PUT next to it moved a visit to 1999 because it took a date it was handed."""
    seen = _fake_core(monkeypatch, lambda r: httpx.Response(200, json={"id": 3002, "salesManager": 80}))
    res = await crm_booking.reassign_visit(3002, 80)
    assert res == {"status": "ok", "sales_manager": 80}
    (req,) = seen
    assert req.method == "PATCH" and req.url.path == "/api/v1/oh/schedule-visits/3002/"
    assert json.loads(req.content) == {"sales_manager": 80}
    assert req.headers["X-CRM-Key"] == "k"


async def test_reassign_explains_an_smid_core_does_not_have(monkeypatch):
    _fake_core(monkeypatch, lambda r: httpx.Response(
        400, json={"salesManager": ['Invalid pk "141" - object does not exist.']}))
    res = await crm_booking.reassign_visit(3002, 141)
    assert res["status"] == "error" and "SMID" in res["detail"]


async def test_reassign_passes_other_errors_through(monkeypatch):
    _fake_core(monkeypatch, lambda r: httpx.Response(404, json={"detail": "No ScheduleVisit matches the given query."}))
    res = await crm_booking.reassign_visit(999, 80)
    assert res == {"status": "error", "detail": "No ScheduleVisit matches the given query."}


def test_the_endpoint_only_moves_upcoming_visits_and_resolves_the_smid_itself():
    src = inspect.getsource(visits_router.reassign)
    assert 'row["status"] != "upcoming"' in src, "a finished visit records who actually went"
    assert "_smid_for_name(req.rm_accompanying)" in src, "never trust an smid from the client"
    assert 'smid == row["smid"]' in src, "same RM must not send Core a no-op write"
    # the mirror into crm_visits and the activity row, same as every other visit action
    assert "smid = :smid, rm_accompanying = :rm" in src
    assert 'action="visit_reassigned"' in src
    route = next(r for r in visits_router.router.routes if r.path == "/visits/{visit_id}/reassign")
    assert route.methods == {"POST"}, "PUT is blocked by CORS here; the visit actions are POST"


# --- brochure -------------------------------------------------------------------------

async def test_brochure_reads_the_camelcase_key_core_really_sends(monkeypatch):
    """Their doc says `brochure_url`; Core sends `brochureUrl` (probed on staging and prod)."""
    seen = _fake_core(monkeypatch, lambda r: httpx.Response(200, json={
        "brochureUrl": "https://storage.googleapis.com/b/home-402/crm/x.pdf",
        "filename": "Property-3 BHK-ABA Cherry County.pdf", "homeId": 402, "source": "crm"}))
    res = await crm_booking.fetch_brochure(402)
    assert res == {"status": "ok", "url": "https://storage.googleapis.com/b/home-402/crm/x.pdf",
                   "filename": "Property-3 BHK-ABA Cherry County.pdf"}
    (req,) = seen
    assert req.method == "GET" and req.url.path == "/api/v1/oh/homes/402/brochure/"
    assert "broker_id" not in str(req.url), "the CRM path must not send a broker"


async def test_an_unknown_home_is_not_found(monkeypatch):
    _fake_core(monkeypatch, lambda r: httpx.Response(404, json={"detail": "No Home matches the given query."}))
    assert (await crm_booking.fetch_brochure(1))["status"] == "not_found"


def test_the_brochure_route_is_a_read_on_the_demand_dashboard():
    route = next(r for r in dd_router.router.routes if r.path == "/demand-dashboard/brochure/{home_id}")
    assert route.methods == {"GET"}
