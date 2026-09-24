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


import re  # noqa: E402
from pathlib import Path  # noqa: E402

API_TS = Path(__file__).parents[2] / "frontend" / "src" / "lib" / "api.ts"


def test_the_dialog_offers_exactly_the_fields_the_server_writes():
    """The Download dialog lists ACTIVITY_EXPORT_FIELDS; the server writes EXPORT_FIELDS.
    A field in one and not the other is a tickbox that 422s, or a column nobody can pick."""
    ts = API_TS.read_text().split("ACTIVITY_EXPORT_FIELDS", 1)[1].split("];", 1)[0]
    frontend = re.findall(r'\["(\w+)",\s*"([^"]+)",\s*(true|false)\]', ts)
    backend = [(k, h, "true" if on else "false") for k, h, on in activity.EXPORT_FIELDS]
    assert frontend == backend


def test_every_export_field_has_a_value():
    """A field listed but not mapped in _export_value is a KeyError on the first row."""
    row = {c: None for c in ("created_at", "actor_name", "actor_email", "actor_role",
                             "entity_type", "entity_id", "lead_name", "lead_phone",
                             "stage_at_time", "action", "field", "before_value", "after_value",
                             "lead_stage_now", "lead_source", "lead_city", "lead_owner", "metadata")}
    for key, _h, _d in activity.EXPORT_FIELDS:
        activity._export_value(key, row)


def test_status_at_the_time_reads_the_neighbouring_stage_changes():
    sql = " ".join(activity.STAGE_AT_TIME.split())
    # the last change at or before the event says what the stage BECAME …
    assert "s.created_at <= a.created_at ORDER BY s.created_at DESC" in sql
    assert "SELECT s.after_value" in sql
    # … else the next change says what it WAS; else the lead's stage now
    assert "s.created_at > a.created_at ORDER BY s.created_at ASC" in sql
    assert "SELECT s.before_value" in sql
    assert sql.rstrip().endswith("l.stage) END AS stage_at_time")
    assert "stage_at_time" not in activity._SELECT, "the table's payload stays as it was"
