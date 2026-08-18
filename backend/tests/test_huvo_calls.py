"""The Huvo call log — filters and lead creation.

Modelled on the Bonvoice call log, but the two datasets answer different questions, so
the filter set is different. Bonvoice records a telephony leg: who dialled, did it
connect, how long. Huvo records what was *said*: the outcome, whether they're
interested, what they're worth. Carrying Bonvoice's filters over unchanged would offer
"placed by" (Huvo has no actor) and "connected" (call_outcome already says far more).
"""
import re

from app.routers.huvo_calls import LINKED_NO, LINKED_YES, NO_CAMPAIGN, calls_filters


def _sql(clause) -> str:
    body = re.sub(r"--[^\n]*", "", str(clause))
    return re.sub(r"\s+", " ", body).strip()


def test_no_filters_means_no_clause():
    clause, params = calls_filters(None, None, None, None, None, None)
    assert clause.strip() == ""
    assert params == {}


def test_search_is_bound_never_inlined():
    """The box is free text straight from the browser and this reaches SQL."""
    clause, params = calls_filters("'; DROP TABLE leads--", None, None, None, None, None)
    assert "DROP TABLE" not in clause
    assert "%'; DROP TABLE leads--%" in params.values()


def test_search_covers_number_name_and_summary():
    """A Huvo row's most searchable content is the call summary — it's the only place
    the conversation itself is recorded."""
    clause, _ = calls_filters("whitefield", None, None, None, None, None)
    src = _sql(clause)
    assert "from_number" in src and "caller_name" in src and "summary" in src


def test_outcome_filters_on_the_exact_value():
    """16 enum values, and it's the field that actually sorts the list into useful
    piles — qualified vs not_reachable vs wrong_number."""
    clause, params = calls_filters(None, "qualified", None, None, None, None)
    assert "call_outcome = :outcome" in _sql(clause)
    assert params["outcome"] == "qualified"


def test_interest_filters_on_the_exact_value():
    clause, params = calls_filters(None, None, "yes", None, None, None)
    assert "is_interested = :interested" in _sql(clause)
    assert params["interested"] == "yes"


def test_linked_splits_calls_that_have_a_lead_from_those_that_dont():
    """846 of the imported rows have no lead. That set IS the create-lead worklist, so
    isolating it is the whole point of this filter."""
    yes, _ = calls_filters(None, None, None, LINKED_YES, None, None)
    no, _ = calls_filters(None, None, None, LINKED_NO, None, None)

    assert "lead_id IS NOT NULL" in _sql(yes)
    assert "lead_id IS NULL" in _sql(no)


def test_an_unknown_linked_value_is_ignored_rather_than_matching_nothing():
    """A stale querystring shouldn't silently show an empty page."""
    clause, _ = calls_filters(None, None, None, "banana", None, None)
    assert "lead_id" not in _sql(clause)


def test_duration_uses_the_same_buckets_as_the_bonvoice_log():
    """Same labels on both pages — a bucket that meant something different here would
    be a trap."""
    clause, params = calls_filters(None, None, None, None, "1-3 mins", None)
    src = _sql(clause)
    assert "duration_sec >=" in src and "duration_sec <" in src
    assert params["dur_lo"] == 60 and params["dur_hi"] == 180


def test_the_open_ended_bucket_has_no_upper_bound():
    clause, params = calls_filters(None, None, None, None, "5+ mins", None)
    assert "duration_sec >=" in _sql(clause)
    assert "dur_hi" not in params


def test_filters_combine_with_and():
    clause, params = calls_filters("rohit", "qualified", "yes", LINKED_NO, "5+ mins", None)
    assert _sql(clause).count(" AND ") >= 4
    assert params["outcome"] == "qualified" and params["interested"] == "yes"


# --- campaign ---------------------------------------------------------------

def test_campaign_filters_on_the_exact_name():
    """Names are free text from Huvo ("CNR_till July 31st"), so this is an equality on
    the stored column, not a LIKE — two campaigns could otherwise share a prefix and
    one would silently include the other."""
    clause, params = calls_filters(None, None, None, None, None, "1st Campaign")
    assert "campaign_name = :campaign" in _sql(clause)
    assert params["campaign"] == "1st Campaign"


def test_campaign_can_isolate_calls_with_no_campaign_at_all():
    """991 rows have none — older deliveries that predate the field. Without a way to
    select them they'd be unreachable except by clearing every filter."""
    clause, params = calls_filters(None, None, None, None, None, NO_CAMPAIGN)
    assert "campaign_name IS NULL" in _sql(clause)
    assert "campaign" not in params


def test_campaign_combines_with_the_other_filters():
    clause, params = calls_filters(None, "qualified", None, LINKED_NO, None, "1st Campaign")
    src = _sql(clause)
    assert "campaign_name = :campaign" in src and "call_outcome = :outcome" in src
    assert "lead_id IS NULL" in src
