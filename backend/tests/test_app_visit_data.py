"""app_visit_data: the response → rows mapping, against the shape Core really returns."""
from app.models import Base
from app.services.app_visit_data import BATCH, rows_from_response

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


def test_the_table_joins_to_crm_visits_by_foreign_key():
    fks = {(fk.parent.name, fk.target_fullname) for fk in Base.metadata.tables["app_visit_data"].foreign_keys}
    assert fks == {("visit_id", "crm_visits.visit_id")}
