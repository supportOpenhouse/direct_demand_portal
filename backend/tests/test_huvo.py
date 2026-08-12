"""Huvo call-update webhook.

Huvo POSTs a completed call to us; we store it and answer 2xx. Their docs define no
authentication at all ("we send the JSON payload without authentication"), so the
shared secret is ours to impose — same `?token=` shape as the Gupshup and Bonvoice
callbacks, because a vendor dashboard that only accepts a URL leaves no other channel.

What this deliberately does NOT do is change a lead. The payload can say
`not_interested` on a lead that's already `won`, and whether a vendor's bot may move
a lead through the funnel is a product decision nobody has made yet. Landing the raw
envelope keeps that decision open and re-derivable.
"""
import pytest
from fastapi import HTTPException

from app.services.huvo import dedupe_key, digits10, extract, parse_dt

ENVELOPE = {
    "status": "completed",
    "call_details": {
        "start_time": "2026-08-11T09:30:00+05:30",
        "end_time": "2026-08-11T09:34:12+05:30",
        "duration_sec": 252,
        "recording_url": "https://cdn.huvo.example/rec/abc.mp3",
        "summary": "short one",
    },
    "analytics_data": {
        "project_name": "Prestige Lakeside", "name": "Rohit Sharma",
        "from_number": "+91 98765 43210", "lead_score": 7.5,
        "is_interested": "yes", "interest_reason": "ready to move",
        "type_of_property": "apartment", "purpose": "end use",
        "location": "Whitefield", "budget_crores": "1.2",
        "site_visit_schedule": "Saturday", "call_outcome_schedule": "Sat 11am",
        "call_outcome_schedule_dt": "2026-08-15T11:00:00+05:30",
        "follow_up_time": "tomorrow evening",
        "follow_up_time_dt": "2026-08-12T18:00:00+05:30",
        "summary_of_call": "Wants a 2BHK in Whitefield, budget 1.2cr.",
        "call_outcome": "qualified", "rsvp_status": "tentative",
        "callback_owner": "bot",
    },
}


# --- phone matching ---------------------------------------------------------

def test_the_number_is_reduced_to_the_last_ten_digits():
    """from_number is the ONLY link back to a lead, and it arrives formatted however
    the caller's carrier reported it. Every other phone comparison in this app matches
    on the last 10 digits; this has to agree with them or nothing will ever join."""
    assert digits10("+91 98765 43210") == "9876543210"
    assert digits10("09876543210") == "9876543210"
    assert digits10("9876543210") == "9876543210"


def test_an_unusable_number_yields_nothing_rather_than_a_bad_match():
    """A short or empty number must not truncate into something that matches the
    wrong lead."""
    assert digits10("12345") == ""
    assert digits10(None) == ""


# --- idempotency ------------------------------------------------------------

def test_the_same_call_twice_produces_the_same_key():
    """There is no delivery id and no retry policy in the contract, so a timeout on
    their side means we see the identical payload again. Without a stable key that's
    a duplicate row and a double-counted call."""
    assert dedupe_key(ENVELOPE) == dedupe_key(dict(ENVELOPE))


def test_two_different_calls_from_one_number_stay_separate():
    """Same buyer, called twice. These are genuinely two calls."""
    later = {**ENVELOPE, "call_details": {**ENVELOPE["call_details"],
                                          "start_time": "2026-08-11T15:00:00+05:30"}}
    assert dedupe_key(ENVELOPE) != dedupe_key(later)


def test_a_call_with_no_start_time_still_gets_a_stable_key():
    """start_time is nullable, so the natural key can't be relied on. Falling back to
    a payload digest still collapses a byte-identical retry, which is the actual
    failure mode."""
    no_start = {**ENVELOPE, "call_details": {**ENVELOPE["call_details"], "start_time": None}}

    assert dedupe_key(no_start)
    assert dedupe_key(no_start) == dedupe_key({**no_start})


# --- timestamps -------------------------------------------------------------

def test_iso_timestamps_are_parsed_to_aware_datetimes():
    assert parse_dt("2026-08-12T18:00:00+05:30").tzinfo is not None


def test_a_human_date_is_not_guessed_at():
    """follow_up_time carries things like 'tomorrow evening'. The _dt field is the
    machine one, and the docs only promise ISO 'when available' — inventing a
    follow-up from prose would put a real callback in an RM's queue at the wrong time."""
    assert parse_dt("tomorrow evening") is None
    assert parse_dt(None) is None
    assert parse_dt("") is None


# --- projection -------------------------------------------------------------

def test_the_analytics_summary_wins_over_the_call_detail_one():
    """Their docs: 'If a field is represented in both call_details and analytics_data,
    the analytics value is retained and the duplicate call-detail field is omitted.'"""
    assert extract(ENVELOPE)["summary"] == "Wants a 2BHK in Whitefield, budget 1.2cr."


def test_budget_in_crores_becomes_lacs():
    """budget_crores is a STRING in their schema, and this app stores lacs. 1 crore is
    100 lacs — copying the number across without the factor understates a budget 100x."""
    assert extract(ENVELOPE)["budget_lacs"] == 120.0


def test_an_unparseable_budget_is_dropped_not_zeroed():
    """'around 2 cr' and '1-1.5' are both legal in a free-text field. A zero would
    read as a real budget of nothing."""
    got = extract({**ENVELOPE, "analytics_data": {**ENVELOPE["analytics_data"],
                                                  "budget_crores": "somewhere near 2"}})
    assert got["budget_lacs"] is None


def test_every_nullable_field_may_be_null_without_blowing_up():
    """All 19 analytics fields are 'required' but 13 are nullable — present is not
    populated. A null must read as 'the caller didn't say', never as a value."""
    nulled = {k: None for k in ENVELOPE["analytics_data"]}
    nulled["summary_of_call"] = "nothing useful"
    got = extract({"status": "completed",
                   "call_details": {k: None for k in ENVELOPE["call_details"]},
                   "analytics_data": nulled})

    assert got["from_number"] == ""
    assert got["budget_lacs"] is None
    assert got["follow_up_at"] is None
    assert got["lead_score"] is None


def test_the_whole_envelope_is_kept_verbatim():
    """lead_score, rsvp_status, interest_reason and purpose have no column here. If
    only the projection were stored, re-deriving after a mapping change would be
    impossible — the data would already be gone."""
    assert extract(ENVELOPE)["payload"] == ENVELOPE


# --- the token --------------------------------------------------------------

def test_a_wrong_token_is_refused(monkeypatch):
    from app.routers import huvo

    monkeypatch.setattr(huvo, "_secret", lambda: "s3cret")
    with pytest.raises(HTTPException) as e:
        huvo.check_token("nope")
    assert e.value.status_code == 403


def test_the_right_token_passes(monkeypatch):
    from app.routers import huvo

    monkeypatch.setattr(huvo, "_secret", lambda: "s3cret")
    huvo.check_token("s3cret")  # must not raise


def test_production_refuses_to_run_the_webhook_unsecured(monkeypatch):
    """This endpoint is public by definition and their default is no auth at all. An
    unsecured URL in prod lets anyone post call outcomes for any phone number."""
    from app.routers import huvo

    monkeypatch.setattr(huvo, "_secret", lambda: "")
    monkeypatch.setattr(huvo, "_is_prod", lambda: True)
    with pytest.raises(HTTPException) as e:
        huvo.check_token(None)
    assert e.value.status_code == 503


def test_an_unset_secret_is_open_in_dev(monkeypatch):
    """Matches the Gupshup callback: unset = open, so local testing needs no setup."""
    from app.routers import huvo

    monkeypatch.setattr(huvo, "_secret", lambda: "")
    monkeypatch.setattr(huvo, "_is_prod", lambda: False)
    huvo.check_token(None)  # must not raise
