"""WhatsApp conversation ownership.

The SQL needs a live Postgres, so these assert the *rules* the SQL encodes — the parts
that would silently distribute work wrongly if someone edited the queries.
"""
import re

from app.services import wa_assign


def _sql(stmt) -> str:
    return re.sub(r"\s+", " ", str(stmt)).strip()


def test_continuity_beats_balance():
    """Rule 1: a number whose lead already has an owner goes to that RM. Without it,
    round-robin puts two RMs on the same customer across two channels."""
    src = _sql(wa_assign._LEAD_OWNER)
    assert "FROM leads" in src
    assert "assigned_to IS NOT NULL" in src
    # matched on the last 10 digits, like every other phone comparison in the app
    assert "right(regexp_replace(phone" in src


def test_rotation_is_load_based_not_turn_based():
    """Rules 2+3: fewest open conversations, then longest-since-assigned. That gives
    round-robin when load is level and self-corrects when it isn't."""
    src = _sql(wa_assign._LEAST_LOADED)
    order = src.split("ORDER BY", 1)[1]
    assert order.index("count(c.phone10)") < order.index("max(c.assigned_at)"), \
        "load must outrank recency, or an idle RM keeps collecting work"
    assert "NULLS FIRST" in order, "a never-assigned RM must sort first"
    assert order.rstrip().endswith("u.name LIMIT 1") or "u.name" in order, \
        "needs a deterministic final tiebreak"


def test_only_active_rms_are_in_the_rotation():
    src = _sql(wa_assign._LEAST_LOADED)
    assert "u.active" in src
    assert "u.role = 'rm'" in src, "admins must not receive assignments"


def test_rejected_contacts_consume_nobody_s_share():
    """A dead number shouldn't count toward an RM's load, or they'd stop getting work."""
    assert "c.tag <> 'rejected'" in _sql(wa_assign._LEAST_LOADED)


def test_assignment_never_overwrites_an_existing_owner():
    """Reshuffling a live conversation confuses the customer more than it helps, so
    the upsert only fills blanks."""
    import inspect
    src = inspect.getsource(wa_assign.assign_if_unassigned)
    assert "WHERE wa_contacts.assigned_to IS NULL" in src
    # and an already-rejected contact is left alone entirely
    assert 'row[1] == "rejected"' in src


def test_backfill_assigns_one_at_a_time():
    """A set-based UPDATE would hand every unowned thread to whichever RM is least
    loaded at that instant — the loop lets each pick see the previous one."""
    import inspect
    src = inspect.getsource(wa_assign.backfill)
    assert "for (p10,) in rows" in src
    assert "assign_if_unassigned" in src


def test_an_inbound_message_does_not_assign_the_conversation():
    """A deliberate reversal, so it gets a guard.

    Arrival used to hand the thread to the least-loaded RM. It no longer does —
    ownership is only ever taken on purpose. Re-adding the call would silently
    restore the old behaviour, and nothing else in the suite would notice.
    """
    import inspect
    from app.routers import gupshup
    assert "assign_if_unassigned" not in inspect.getsource(gupshup._persist)


def test_assignment_still_happens_when_something_asks_for_it():
    """The other half: not-on-arrival must not become not-at-all. Converting a chat
    with `assign=true` still routes through the same one definition of ownership."""
    import inspect
    from app.routers import gupshup
    assert "assign_if_unassigned" in inspect.getsource(gupshup._designated_rm)
