"""WhatsApp page CSV: one row per conversation — name, phone, every message as JSON."""
import inspect
from datetime import datetime, timezone

from app.routers import gupshup
from app.routers.gupshup import export_rows


def _m(phone, direction, body, at, name=None, msg_type="text"):
    return {"phone": phone, "direction": direction, "body": body, "msg_type": msg_type,
            "name": name, "created_at": at}


T = lambda h, m=0: datetime(2026, 10, 7, h, m, tzinfo=timezone.utc)  # noqa: E731


def test_one_row_per_conversation_messages_oldest_first_in_ist():
    rows = export_rows([
        _m("919876543210", "out", "Yes, ready", T(9, 45)),
        _m("919876543210", "in", "Is it ready?", T(9, 42), name="Ravi"),
        _m("918888888888", "in", "Hi", T(8, 0)),
    ])
    assert [r["phone"] for r in rows] == ["919876543210", "918888888888"], "most recent conversation first"
    ravi = rows[0]
    assert ravi["name"] == "Ravi"
    assert ravi["messages"] == [
        {"at": "2026-10-07 15:12 IST", "from": "customer", "type": "text", "text": "Is it ready?"},
        {"at": "2026-10-07 15:15 IST", "from": "us", "type": "text", "text": "Yes, ready"},
    ]
    assert rows[1]["name"] is None


def test_the_name_is_the_newest_inbound_one():
    rows = export_rows([_m("91", "in", "a", T(8), name="Old"), _m("91", "in", "b", T(9), name="New"),
                        _m("91", "out", "c", T(10), name="Agent")])
    assert rows[0]["name"] == "New", "our own outbound rows never name the customer"


def test_the_export_is_scoped_like_every_other_read():
    assert "_scoped(" in inspect.getsource(gupshup.gupshup_export)


def test_only_admins_can_export():
    """Every CSV export in the app is admin-only; this one returns the whole inbox in
    bulk, so the gate is on the server, not just the button."""
    from app.core.auth import require_admin
    dep = inspect.signature(gupshup.gupshup_export).parameters["user"].default
    assert dep.dependency is require_admin
