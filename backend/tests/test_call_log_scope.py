"""RM access to the Bonvoice Call Log.

The page was admin-only. RMs can see it now, but only their own calls — and "their
own" has to be defined on the phone number, not on `placed_by`: an INBOUND call has
no actor at all (the lead dialled us), and those are exactly the ones an RM most
needs to see.
"""
import re

from app.routers.bonvoice import incoming_only_sql, own_calls_sql


def _sql(x) -> str:
    return re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", str(x))).strip()


def test_an_rm_sees_a_call_on_any_leg_of_their_own_number():
    """Bonvoice puts the handset in source on an outgoing row and in destination on an
    incoming one, and DisplayNumber is whichever side we showed. Checking one field
    would hide half an RM's calls."""
    src = _sql(own_calls_sql())
    for col in ("c.source_number", "c.destination_number", "c.display_number"):
        assert col in src


def test_own_calls_matches_on_the_last_ten_digits():
    """users.phone holds '919999999999', Bonvoice reports '9220633844'. Anything but a
    last-10 compare and an RM sees none of their calls."""
    assert "right(regexp_replace" in _sql(own_calls_sql())


def test_own_calls_binds_the_number():
    assert ":me10" in _sql(own_calls_sql())


def test_incoming_is_decided_by_direction_not_by_who_placed_it():
    """placed_by is NULL on an inbound call — using it to infer direction would mark
    every dropped-callback row as incoming."""
    src = _sql(incoming_only_sql())
    assert "direction" in src.lower()
    assert "placed_by" not in src


def test_incoming_tolerates_the_two_spellings_bonvoice_uses():
    """Records say 'incoming'; some callbacks say 'inbound'. A prefix match covers
    both — matching either word exactly would silently drop the other."""
    src = _sql(incoming_only_sql()).lower()
    assert "like 'in%'" in src
    # and case can't matter: the column holds 'Incoming' on some rows
    assert "lower(" in src
