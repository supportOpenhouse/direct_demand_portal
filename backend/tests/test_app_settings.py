"""Org-wide app settings.

One row per setting, admin-writable, readable by everyone — an RM's browser has to
know whether to hide lead phone numbers, and only an admin may decide that.

The keys are a fixed whitelist rather than a free kv: this is reachable from a
browser, and an open key space turns one endpoint into arbitrary writes to a shared
table.
"""
import pytest

from app.services.app_settings import DEFAULTS, SETTING_KEYS, coerce, merge_defaults


def test_hiding_lead_phones_is_a_known_setting():
    assert "hide_lead_phones" in SETTING_KEYS


def test_it_defaults_to_showing_phone_numbers():
    """Turning this on is a deliberate act. A fresh install must not silently hide
    the numbers RMs work from."""
    assert DEFAULTS["hide_lead_phones"] is False


def test_an_unknown_key_is_rejected():
    """The endpoint is browser-reachable — an open key space would let any signed-in
    admin write arbitrary rows into a shared table."""
    with pytest.raises(KeyError):
        coerce("drop_everything", True)


def test_stored_values_round_trip_as_real_booleans():
    """Stored as text, read back as JSON. 'false' is a non-empty string and would be
    truthy in the browser — that's how a hide-flag ends up stuck on."""
    assert coerce("hide_lead_phones", "true") is True
    assert coerce("hide_lead_phones", "false") is False
    assert coerce("hide_lead_phones", True) is True
    assert coerce("hide_lead_phones", False) is False


def test_a_missing_or_junk_stored_value_falls_back_to_the_default():
    """A hand-edited row must not decide policy by accident."""
    assert coerce("hide_lead_phones", None) is False
    assert coerce("hide_lead_phones", "") is False
    assert coerce("hide_lead_phones", "yes please") is False


def test_reading_settings_fills_in_every_key_that_has_no_row():
    """The frontend reads one object and indexes into it. A key missing from the
    response would read as undefined — neither true nor false — and the toggle would
    render empty."""
    assert merge_defaults({}) == DEFAULTS
    assert merge_defaults({"hide_lead_phones": "true"})["hide_lead_phones"] is True
