"""Which pulled Bonvoice records are actually ours.

The account returns call records that aren't this app's, and until now the only
filter was "has a callID" — so everything landed in the call log.

The proper key is the DID, but the records we're receiving right now don't carry it.
Until they do, ownership is inferred from the two fields that ARE populated:

  * `Agent` — on an OUTGOING record this is the RM's own handset (Click2Call rings it
    first), so a match means one of our people placed the call;
  * `DestinationNumber` — on an INCOMING record this is the number that was dialled,
    which for us is the DID.

One field per direction, which is why both are checked rather than either alone.
"""
from app.routers.bonvoice import is_ours

RM_PHONES = {"8003297088", "9876543210"}
DID = "7946350641"

OUTGOING = {
    "Agent": "8003297088",            # our RM's handset
    "DestinationNumber": "8595594789",  # the customer
    "CallDirection": "outgoing",
}


def test_an_outgoing_call_from_one_of_our_rms_is_ours():
    assert is_ours(OUTGOING, RM_PHONES, DID)


def test_an_incoming_call_to_our_did_is_ours():
    """Inbound, the RM's handset isn't in Agent — the DID is what was dialled."""
    assert is_ours({"Agent": None, "DestinationNumber": DID, "CallDirection": "incoming"},
                   RM_PHONES, DID)


def test_a_call_belonging_to_somebody_else_is_not_ours():
    """The whole point: another tenant's call on the same account must not land in
    our call log."""
    assert not is_ours({"Agent": "9999999999", "DestinationNumber": "8888888888"},
                       RM_PHONES, DID)


def test_the_did_is_matched_in_either_field():
    """Direction isn't always reported, so neither field is assumed."""
    assert is_ours({"Agent": DID, "DestinationNumber": "8595594789"}, RM_PHONES, DID)


def test_matching_ignores_formatting():
    """These numbers arrive as 8003297088, 08003297088 and +918003297088 depending on
    the record — the same last-10 rule every other phone comparison here uses."""
    assert is_ours({"Agent": "+91 80032 97088", "DestinationNumber": None}, RM_PHONES, DID)
    assert is_ours({"Agent": "08003297088", "DestinationNumber": None}, RM_PHONES, DID)


def test_an_empty_record_is_not_ours():
    assert not is_ours({}, RM_PHONES, DID)
    assert not is_ours({"Agent": "", "DestinationNumber": None}, RM_PHONES, DID)


def test_with_no_rms_and_no_did_nothing_is_claimed():
    """Fail closed. If the RM list can't be read, importing everything would be worse
    than importing nothing — the log is meant to be this team's calls."""
    assert not is_ours(OUTGOING, set(), "")
