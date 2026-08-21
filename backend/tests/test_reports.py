"""Per-RM daily report.

Everything is derived from activity_log, so the report can only ever be as good as
the instrumentation — which is why the events were added first.

The one structural trap: the date filter has to live in the JOIN, not the WHERE. An
RM who did nothing today is the single most important row in a report, and a WHERE on
a LEFT JOIN's right-hand table silently drops exactly those people.
"""
import re

from app.routers.reports import RM_REPORT, _metric_sql


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
