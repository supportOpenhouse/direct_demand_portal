"""Round-robin assignment of new leads.

The SQL needs a live Postgres, so these assert the *rules* it encodes — the parts that
would silently distribute work wrongly if someone edited the queries.
"""
import inspect
import re

from app.models import User
from app.services import lead_assign


def _sql(stmt) -> str:
    """Collapsed SQL with comments stripped — the prose here explains the very values
    being asserted on, so a needle would otherwise match the comment, not the code."""
    return re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", str(stmt))).strip()


def test_users_city_is_an_array_and_never_null():
    """`= ANY(NULL)` is NULL, not false — a nullable column would make an RM silently
    match no city at all rather than 'covers nothing specific'."""
    col = User.__table__.columns["city"]
    assert col.type.__class__.__name__ == "ARRAY"
    assert col.nullable is False
    assert col.server_default is not None


def test_todays_count_lives_in_the_join_not_the_where():
    """The one structural trap. An RM who has taken nothing today is exactly who this
    query is looking for; a WHERE on a LEFT JOIN's right-hand table drops them, and the
    sweep would then hand every lead to whoever already has the most."""
    src = _sql(lead_assign.PICK_RM)
    join = src.split("LEFT JOIN leads l", 1)[1].split("WHERE", 1)[0]
    assert "Asia/Kolkata" in join, "the day window must be part of the JOIN"
    assert "assigned_at" in join


def test_the_balance_is_today_not_lifetime():
    """Lifetime totals are what give a new joinee every lead on their first day — they
    sit at zero and stay bottom of the ordering until they catch up on everyone's
    history. The IST day resets that for the whole team at midnight."""
    src = _sql(lead_assign.PICK_RM)
    assert "count(l.id)" in src
    assert "(now() AT TIME ZONE 'Asia/Kolkata')::date" in src


def test_ties_break_deterministically():
    """Two RMs level on today's count must not depend on row order: longest-since-last
    wins, never-assigned first, then name."""
    src = _sql(lead_assign.PICK_RM)
    order = src.split("ORDER BY", 1)[1]
    assert order.index("count(l.id)") < order.index("max(l.assigned_at)") < order.index("u.name")
    assert "NULLS FIRST" in order


def test_a_test_rm_is_never_given_a_real_buyer():
    """Exactly 'rm', not CALLING_ROLES — a test_rm is dialled by campaigns but owning a
    real lead would hide that buyer from everyone who could actually work them."""
    src = _sql(lead_assign.PICK_RM)
    assert "u.role = 'rm'" in src and "test_rm" not in src
    assert "u.active" in src


def test_city_match_is_case_insensitive_and_cast():
    """`IS NULL` on a bare asyncpg parameter raises AmbiguousParameterError; and an
    admin typing 'gurgaon' must still match a lead normalised to 'Gurgaon'."""
    src = _sql(lead_assign.PICK_RM)
    assert "CAST(:city AS text) IS NULL" in src
    assert "lower(c) = lower(CAST(:city AS text))" in src


def test_an_uncovered_city_widens_the_pool_instead_of_narrowing_to_nobody():
    """The user's second rule. Scoping an unknown city to the RMs who cover it would
    match zero RMs and leave the lead unassigned forever."""
    src = inspect.getsource(lead_assign.pick_rm)
    assert "if key and key in covered else None" in src


def test_valid_cities_come_from_the_roster_not_a_hardcoded_list():
    """A city is valid exactly when an active RM covers it, so adding Faridabad to an
    RM's array makes it valid with no code change — and no second list to drift."""
    src = _sql(lead_assign.COVERED_CITIES)
    assert "unnest(u.city)" in src and "u.active" in src
    # Against the COMMENT-STRIPPED sql, not the raw string: the comments here explain
    # the city rule using real city names, so a raw scan fails on its own prose.
    for hardcoded in ("Gurgaon", "Noida", "Ghaziabad"):
        assert hardcoded not in src
        assert hardcoded not in _sql(lead_assign.PICK_RM)


def test_the_sweep_assigns_one_at_a_time():
    """A set-based UPDATE would evaluate every pick against the same starting counts and
    hand the whole backlog to whichever RM is lowest right now."""
    src = inspect.getsource(lead_assign.run_assignment_sweep)
    assert "for lead_id, city in leads" in src
    assert "await pick_rm(" in src


def test_the_claim_cannot_steal_a_lead_someone_else_took():
    """Re-checking `assigned_to IS NULL` in the UPDATE makes the write a no-op if a
    human on the Leads page grabbed it between the read and the write."""
    src = _sql(lead_assign.CLAIM)
    assert "assigned_to IS NULL" in src
    assert "RETURNING" in src
    assert "assigned_at = now()" in src, "the round-robin reads assigned_at; it must be set"


def test_the_sweep_skips_test_leads_and_takes_the_oldest_first():
    src = _sql(lead_assign.UNASSIGNED)
    assert "assigned_to IS NULL" in src and "NOT is_test" in src
    assert "ORDER BY received_at NULLS LAST" in src
    assert ":limit" in src


def test_every_auto_assignment_is_logged():
    """Reports counts `assigned` events. A lead that changes owner with no row is work
    that never happened as far as the page is concerned."""
    src = inspect.getsource(lead_assign.run_assignment_sweep)
    assert 'action="assigned"' in src
    assert '"auto_round_robin"' in src
