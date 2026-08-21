"""Per-RM daily report.

Everything is derived from activity_log, so the report can only ever be as good as
the instrumentation — which is why the events were added first.

The one structural trap: the date filter has to live in the JOIN, not the WHERE. An
RM who did nothing today is the single most important row in a report, and a WHERE on
a LEFT JOIN's right-hand table silently drops exactly those people.
"""
import re

import pytest
from fastapi import HTTPException

from app.routers.reports import (
    RM_DAY_LEADS,
    RM_DAYS,
    RM_REPORT,
    _metric_sql,
    _scoped_email,
)


def _sql(x) -> str:
    return re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", str(x))).strip()


def test_an_rm_with_no_activity_still_appears():
    """A blank row IS the finding. Filtering the date in WHERE would turn this report
    into "people who were busy", which is the opposite of what it's for."""
    src = _sql(RM_REPORT)
    join = src.split("LEFT JOIN activity_log", 1)[1].split("GROUP BY", 1)[0]

    assert "Asia/Kolkata" in join, "the day window must be part of the join"
    assert "WHERE" not in join.split("GROUP BY")[0].upper().replace("WHERE U.", "")


def test_the_report_covers_calling_roles_only():
    """Admins don't take calls; a row of zeroes for every admin is noise."""
    src = _sql(RM_REPORT)
    assert "'rm'" in src and "'test_rm'" in src


def test_login_is_the_first_action_of_the_day():
    """Not the `login` event: a week-long JWT means someone can work for days without
    signing in, and their row would read blank."""
    assert "min(a.created_at)" in _sql(RM_REPORT).lower()


def test_days_are_ist_calendar_days():
    """The team works IST. A UTC day boundary would put the 05:30 either side of
    midnight on the wrong day's report."""
    assert _sql(RM_REPORT).count("Asia/Kolkata") >= 1


def test_each_metric_counts_only_its_own_action():
    assert "action = 'call_connected'" in _sql(_metric_sql("calls_connected"))
    assert "action = 'call_missed'" in _sql(_metric_sql("calls_missed"))


def test_stage_metrics_match_the_destination_not_just_the_verb():
    """Every one of these is a stage_change. Counting the verb alone would give the
    same number four times."""
    for metric, stage in [("leads_qualified", "qualified"),
                          ("visit_scheduled", "visit_scheduled"),
                          ("revisit_booked", "revisit_scheduled"),
                          ("leads_rejected", "rejected")]:
        src = _sql(_metric_sql(metric))
        assert "action = 'stage_change'" in src
        assert f"after_value = '{stage}'" in src


def test_calls_dialled_is_derived_not_a_separate_action():
    """Bonvoice's own connected flag isn't trusted for this — the report counts what
    the RM marked. call_dialled is stored, but deliberately not counted here."""
    src = _sql(_metric_sql("calls_dialled"))
    assert "call_connected" in src and "call_missed" in src
    assert "call_dialled" not in src


# --- the All range ----------------------------------------------------------

def test_all_time_resolves_from_the_log_not_a_hardcoded_date():
    """"All" has to start where the data starts. A hardcoded floor like 2020-01-01
    would report a range the log can't back, and the page header would lie about what
    it's showing."""
    from app.routers.reports import EARLIEST_ACTIVITY

    src = _sql(EARLIEST_ACTIVITY)
    assert "min(created_at)" in src.lower()
    assert "activity_log" in src
    assert "Asia/Kolkata" in src, "the floor is an IST calendar day like every other bound"


# ── the per-RM drill-down ────────────────────────────────────────────────────────
# Different trap from the summary above. Here the date filter belongs in the WHERE —
# a day with no work has no row to preserve — so what needs pinning instead is the
# scoping, the ordering of the stage journey, and the direction of the uuid cast.
def test_the_drill_down_is_scoped_to_one_actor():
    """Both queries name a single actor. Dropping this clause would turn a per-RM
    page into every RM's leads and notes, which is a different product."""
    for q in (RM_DAYS, RM_DAY_LEADS):
        assert "lower(a.actor_email) = lower(:email)" in _sql(q)


def test_the_drill_down_days_are_ist_calendar_days():
    """Same reason as the summary: a UTC boundary rolls the day at 05:30 IST, which
    is mid-shift — half a morning's calls would land on the previous row."""
    for q in (RM_DAYS, RM_DAY_LEADS):
        assert "Asia/Kolkata" in _sql(q)


def test_the_stage_journey_is_ordered_by_time_not_by_name():
    """min()/max() on before_value/after_value looks right and is wrong: it sorts the
    stage NAMES alphabetically, so a lead that went new → qualified → rejected would
    report 'new → rejected' by luck and 'qualified → won' when the luck runs out."""
    src = _sql(RM_DAY_LEADS)
    journey = src.split("from_stage", 1)[0].split("count(*)", 1)[1]
    assert "array_agg" in journey and "ORDER BY a.created_at" in journey
    assert "min(a.before_value)" not in src and "max(a.after_value)" not in src


def test_the_lead_join_casts_the_uuid_to_text():
    """entity_id is TEXT and holds non-uuid keys ('leads_sheet'), so casting it to
    uuid raises on the first sync row. A regex guard does not save you — AND order in
    a JOIN isn't guaranteed and the planner can still run the cast first."""
    src = _sql(RM_DAY_LEADS)
    assert "l.id::text = a.entity_id" in src
    assert "a.entity_id::uuid" not in src


def test_the_day_list_counts_leads_not_events():
    """'12 leads' and '84 actions' are different numbers and the page shows both."""
    assert "count(DISTINCT a.entity_id)" in _sql(RM_DAYS)


def test_an_rm_only_ever_opens_their_own_report():
    """The querystring is a request, not an authorisation. Someone who can read the
    page can edit the URL."""
    assert _scoped_email({"role": "rm", "email": "Me@oh.in"}, "boss@oh.in") == "me@oh.in"
    assert _scoped_email({"role": "test_rm", "email": "t@oh.in"}, None) == "t@oh.in"


def test_an_admin_asking_for_nobody_fails_closed():
    """Falling back to 'everyone' would silently widen the page instead of erroring."""
    assert _scoped_email({"role": "admin", "email": "a@oh.in"}, "rm@oh.in") == "rm@oh.in"
    with pytest.raises(HTTPException):
        _scoped_email({"role": "admin", "email": "a@oh.in"}, None)
