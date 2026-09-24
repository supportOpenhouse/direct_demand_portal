"""Activity Logs: the lead's phone goes in the CSV, never in the table's payload."""
from app.routers import activity


def test_the_phone_is_in_the_export_only():
    # the list endpoint feeds the page — anything it selects reaches every browser
    assert "phone" not in activity._SELECT
    assert "l.phone AS lead_phone" in activity._EXPORT_SELECT


def test_export_and_list_read_the_same_rows():
    """Only the column list differs, so a filter can never make the CSV disagree with
    the table about WHICH events it holds."""
    assert activity._SELECT.endswith(activity._FROM)
    assert activity._EXPORT_SELECT.endswith(activity._FROM)
