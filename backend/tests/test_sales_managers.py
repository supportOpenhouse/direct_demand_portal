"""sales_manager_list: Core's RM roster, kept current, never deleted from."""
from datetime import datetime, timezone

import httpx
import pytest

from app.models import SalesManagerList
from app.services import sales_managers as svc

# trimmed from the real staging response, 25 Sep — camelCase, whatever the doc says
REAL = {"salesManagers": [
    {"id": 69, "name": "Aaysha", "mobile": "8000000046", "cityId": 3, "cityName": "Noida", "isActive": True},
    {"id": 80, "name": "Sales Test", "mobile": "", "cityId": 2, "cityName": "Gurgaon", "isActive": True},
]}
NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)


def test_rows_read_the_keys_core_really_sends():
    rows = svc.rows_from_response(REAL, NOW)
    assert rows[0] == {"id": 69, "name": "Aaysha", "mobile": "8000000046", "city_id": 3,
                       "city_name": "Noida", "is_active": True, "data": REAL["salesManagers"][0],
                       "fetched_at": NOW}
    assert rows[1]["mobile"] is None, "a blank mobile is stored as missing, not as ''"


def test_every_row_key_is_a_column_of_the_table():
    """A key the service fills that the model lacks fails every upsert."""
    cols = set(SalesManagerList.__table__.columns.keys())
    assert set(svc.rows_from_response(REAL, NOW)[0]) <= cols
    assert "first_seen_at" in cols and "first_seen_at" not in svc.rows_from_response(REAL, NOW)[0], \
        "first_seen_at is set once by the DB default and never rewritten"


def test_a_manager_who_drops_out_is_deactivated_not_deleted():
    sql = " ".join(svc.DEACTIVATE_MISSING.text.split())
    assert sql.startswith("UPDATE sales_manager_list SET is_active = false")
    assert "NOT (id = ANY(:seen))" in sql
    assert "DELETE" not in sql.upper()


async def test_an_empty_roster_is_refused_rather_than_deactivating_everyone(monkeypatch):
    async def empty():
        return []
    monkeypatch.setattr(svc, "fetch_sales_managers", empty)
    with pytest.raises(RuntimeError, match="refusing"):
        await svc.refresh_sales_managers(apply=True)


async def test_a_failed_request_raises_instead_of_storing_nothing(monkeypatch):
    """Prod answered an HTML 404 on 25 Sep (route not deployed). That must stop the run."""
    monkeypatch.setattr(svc, "_client", lambda: httpx.AsyncClient(
        base_url="https://core.test/api/v1/oh/",
        transport=httpx.MockTransport(lambda r: httpx.Response(404, text="<html>Not Found</html>"))))
    with pytest.raises(RuntimeError, match="404"):
        await svc.fetch_sales_managers()
