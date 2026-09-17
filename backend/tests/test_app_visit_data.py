"""app_visit_data: the response → rows mapping, against the shape Core really returns."""
import re
from datetime import date
from pathlib import Path

from app.models import Base
from app.services.app_visit_data import (
    BATCH,
    DATE_COLUMNS,
    HIDDEN_FIELDS,
    INT_COLUMNS,
    SM_COLUMNS,
    TEXT_COLUMNS,
    _project,
    rows_from_response,
)

REAL_SHAPE = {  # trimmed from a real prod response, 15 Sep
    "visits": [{
        "id": 18005, "status": "completed", "leadStatus": "warm",
        "updatedAt": "2026-09-14T11:03:46.218035+00:00",
        "demandSmFeedback": {"closingSignal": None}, "allFeedback": [],
    }],
    "missingIds": [99999999],   # camelCase — NOT missing_ids, as the announcement said
}


def test_found_visits_are_stored_whole():
    found, _ = rows_from_response(REAL_SHAPE)
    assert [r["visit_id"] for r in found] == [18005]
    assert found[0]["found"] is True
    assert found[0]["data"] == REAL_SHAPE["visits"][0], "verbatim, nested objects included"
    assert found[0]["crm_updated_at"].year == 2026


def test_missing_ids_are_flagged_without_touching_data():
    _, missing = rows_from_response(REAL_SHAPE)
    assert missing == [{"visit_id": 99999999, "found": False, "fetched_at": missing[0]["fetched_at"]}]
    assert "data" not in missing[0], "a visit gone missing at Core keeps its last copy"


def test_batches_stay_within_the_api_limit():
    assert BATCH == 100


def test_the_json_is_projected_into_columns():
    """Typed, not text: a date is a date and a count an int, so the columns can be
    filtered and sorted without re-parsing the JSON."""
    row = _project({
        "status": "completed", "leadStatus": "warm", "selectedDate": "2026-09-14",
        "visitDate": None, "createdAt": "2026-09-14T11:01:38.781647+00:00",
        "homeId": "564", "floor": 3, "leadOccurrenceCount": 6, "salesManagerId": "137",
        "demandSmFeedback": {"closingSignal": "Non-committal"}, "allFeedback": [],
    })
    assert row["status"] == "completed" and row["lead_status"] == "warm"
    assert row["selected_date"] == date(2026, 9, 14)
    assert row["visit_date"] is None, "a null date stays null, not the string 'None'"
    assert row["crm_created_at"].year == 2026
    assert row["home_id"] == 564 and row["floor"] == 3 and row["sales_manager_id"] == 137
    assert row["sm_closing_signal"] == "Non-committal"
    assert row["sm_price_discussion"] is None, "a key the feedback object omits"
    assert row["all_feedback"] == []


def test_a_blank_id_is_null_not_a_crash():
    """Core sends "" for an absent id, not null — seen on staging's salesManagerId.
    int("") raises, and one such visit would take down the whole batch's upsert."""
    row = _project({"salesManagerId": "", "homeId": "73", "floor": None})
    assert row["sales_manager_id"] is None
    assert row["home_id"] == 73 and row["floor"] is None


def test_a_visit_without_sm_feedback_projects_nulls():
    """demandSmFeedback is null on most visits — that must not blow up the fill."""
    row = _project({"status": "upcoming", "demandSmFeedback": None})
    assert all(row[c] is None for c in SM_COLUMNS)


def test_the_columns_the_service_fills_are_the_columns_the_model_has():
    """The SQL, the model and the mapping are three copies of one list. This fails the
    moment they drift — a column the service fills that the table lacks is an error
    every refresh, and one the model lacks is invisible to every query."""
    mapped = set(TEXT_COLUMNS) | set(DATE_COLUMNS) | set(INT_COLUMNS) | set(SM_COLUMNS)
    mapped |= {"crm_created_at", "all_feedback"}
    base = {"visit_id", "found", "data", "crm_updated_at", "fetched_at"}
    model = set(Base.metadata.tables["app_visit_data"].columns.keys())
    assert mapped | base == model, f"drifted from the model: {mapped ^ (model - base)}"

    sql = (Path(__file__).parents[1] / "scripts" / "15_app_visit_data_columns.sql").read_text()
    added = set(re.findall(r"ADD COLUMN IF NOT EXISTS\s+(\w+)", sql))
    assert added == mapped, f"drifted from the SQL: {added ^ mapped}"


def test_the_hidden_fields_are_stored_but_never_served():
    """Five fields stay in the table — it is Core's record — but must not reach the UI.
    This fails the moment a router starts selecting one, which is the only way they could
    leak: nothing serves app_visit_data today, so the rule has to outlive the gap between
    now and whoever builds that view."""
    table = set(Base.metadata.tables["app_visit_data"].columns.keys())
    assert HIDDEN_FIELDS <= table, "hiding a field that isn't a column is a typo, not a rule"

    def leaks(src: str) -> set[str]:
        """Hidden fields named by a source file that serves visit data. Both spellings
        count: a router can reach the table through the ORM model without ever writing
        its name — which is exactly what /visits/{id}/details does."""
        if "app_visit_data" not in src and "AppVisitData" not in src:
            return set()  # this file doesn't serve visit data at all
        return {f for f in HIDDEN_FIELDS if re.search(rf"\b{f}\b", src)}

    assert leaks("SELECT visit_id, broker_name FROM app_visit_data") == {"broker_name"}
    assert leaks("from ..models import AppVisitData\nSELECT broker_name") == {"broker_name"}
    assert leaks("SELECT visit_id, broker_name FROM crm_visits") == set(), "other tables are not this rule's business"
    assert leaks("SELECT visit_id, city FROM app_visit_data") == set()

    # the endpoint that serves them builds its column list from the model MINUS
    # HIDDEN_FIELDS, so this holds no matter what columns are added later
    from app.routers.visits import _detail_columns
    assert not (set(_detail_columns()) & HIDDEN_FIELDS)

    routers = Path(__file__).parents[1] / "app" / "routers"
    for py in routers.rglob("*.py"):
        assert not leaks(py.read_text()), \
            f"{py.name} exposes {leaks(py.read_text())}, hidden from the UI on purpose"


def test_the_table_has_no_foreign_key_to_crm_visits():
    """It holds EVERY Openhouse visit now. crm_visits only has the ones we booked, so a
    foreign key would reject every other visit — and take its whole insert batch with it."""
    assert not Base.metadata.tables["app_visit_data"].foreign_keys
    assert Base.metadata.tables["app_visit_data"].primary_key.columns.keys() == ["visit_id"]


async def test_repeats_across_pages_are_dropped_keeping_the_newest():
    """Offset paging over a table still being written to can return one visit twice, and a
    repeat inside a single INSERT … ON CONFLICT DO UPDATE is a hard Postgres error."""
    from app.services.app_visit_data import fetch_all_visits

    pages = {
        0: {"visits": [{"id": 1, "updatedAt": "2026-09-01"}, {"id": 2, "updatedAt": "2026-09-01"}],
            "pagination": {"hasMore": True, "nextOffset": 2}},
        2: {"visits": [{"id": 2, "updatedAt": "2026-09-05"}, {"id": 3, "updatedAt": "2026-09-01"}],
            "pagination": {"hasMore": False, "nextOffset": 4}},
    }

    class Resp:
        def __init__(self, body): self.body = body
        def raise_for_status(self): pass
        def json(self): return self.body

    class Client:
        async def get(self, path, params):
            assert path == "crm/all-visits/" and params["limit"] == 50
            return Resp(pages[params["offset"]])

    visits, repeats = await fetch_all_visits(Client())
    assert sorted(int(v["id"]) for v in visits) == [1, 2, 3]
    assert repeats == 1
    assert next(v for v in visits if v["id"] == 2)["updatedAt"] == "2026-09-05", "keeps the newer copy"


async def test_a_page_that_does_not_advance_stops_the_walk():
    """A server bug that answers hasMore with the same offset would loop forever."""
    import pytest

    from app.services.app_visit_data import fetch_all_visits

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"visits": [], "pagination": {"hasMore": True, "nextOffset": 0}}

    class Client:
        async def get(self, path, params): return Resp()

    with pytest.raises(RuntimeError, match="did not advance"):
        await fetch_all_visits(Client())
