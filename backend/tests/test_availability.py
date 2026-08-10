"""Live Inventory status comes from demand_details, not the sheet.

The sheet's listing_status is what supply typed when the unit was listed; it goes
stale the moment something is booked. demand_details.availability_status is the live
truth, joined on supply_form_uid -> uid.

Fallback matters more than the join: a unit with no match must keep showing its sheet
status, never a blank tag. 33 of 186 rows have no match today.
"""
import re

from app.services.availability import apply_availability


def _sql(stmt) -> str:
    body = re.sub(r"--[^\n]*", "", str(stmt))
    return re.sub(r"\s+", " ", body).strip()


def _item(status, uid=None):
    return {"status": status, "raw": {"supply_form_uid": uid} if uid is not None else {}}


def test_a_matched_unit_shows_the_live_status():
    items = [_item("Ready", "OHGHC1416")]

    assert apply_availability(items, {"OHGHC1416": "Booked"}) == 1
    assert items[0]["status"] == "Booked"


def test_an_unmatched_unit_keeps_its_sheet_status():
    """The explicit requirement. 33 of 186 rows land here — blanking them would wipe
    the tag off a sixth of the page."""
    items = [_item("Coming Soon", "OHGHC9999")]

    assert apply_availability(items, {"OHGHC1416": "Available"}) == 0
    assert items[0]["status"] == "Coming Soon"


def test_a_unit_with_no_supply_form_uid_keeps_its_sheet_status():
    """30 sheet rows have the column blank."""
    items = [_item("Ready")]

    assert apply_availability(items, {"OHGHC1416": "Available"}) == 0
    assert items[0]["status"] == "Ready"


def test_a_blank_live_status_does_not_erase_the_tag():
    """availability_status is nullable. An empty string is not an answer — falling
    through to the sheet beats rendering a unit with no status at all."""
    for empty in (None, "", "   "):
        items = [_item("Ready", "OHGHC1416")]
        assert apply_availability(items, {"OHGHC1416": empty}) == 0
        assert items[0]["status"] == "Ready"


def test_matching_ignores_surrounding_whitespace_on_the_sheet_id():
    """supply_form_uid is hand-entered in a spreadsheet."""
    items = [_item("Ready", "  OHGHC1416 ")]

    assert apply_availability(items, {"OHGHC1416": "Sold"}) == 1
    assert items[0]["status"] == "Sold"


def test_the_lookup_binds_the_uid_list():
    """The ids come from a sheet anyone in ops can edit — they reach the other
    database, so they must travel as a bound parameter, never inlined."""
    from app.services.availability import _AVAILABILITY

    src = _sql(_AVAILABILITY)
    assert "uid = ANY(:uids)" in src
    assert "demand_details" in src


def test_it_reads_the_uid_off_a_real_map_rows_row():
    """apply_availability digs into raw["supply_form_uid"], and map_rows is what builds
    that dict. If the sync ever stopped keeping every sheet column in `raw`, the join
    would quietly match nothing and every unit would look Ready forever."""
    from app.services.availability import uids_of
    from app.services.inventory_sync import map_rows

    rows = map_rows([
        ["home_id", "supply_form_uid", "property_name", "listing_status"],
        ["403", "OHGHC1416", "A Tower", "Ready"],
        ["404", "", "B Tower", "Coming Soon"],
    ])

    assert uids_of(rows) == ["OHGHC1416"]
    assert apply_availability(rows, {"OHGHC1416": "Sold"}) == 1
    assert [r["status"] for r in rows] == ["Sold", "Coming Soon"]


async def test_the_sync_writes_the_live_status_into_the_rows_it_inserts(monkeypatch):
    """The point of doing this at sync time: inventory_units.status is what the
    matching engine reads (_all_units in services/matching.py). Left as the sheet
    value, the matcher recommends flats that already sold."""
    from app.services import inventory_sync

    monkeypatch.setattr(inventory_sync, "live_statuses",
                        lambda uids: _immediate({"OHGHC1416": "Booked"}))

    rows = inventory_sync.map_rows([
        ["home_id", "supply_form_uid", "property_name", "listing_status"],
        ["403", "OHGHC1416", "A Tower", "Ready"],
        ["404", "OHGHC9999", "B Tower", "Ready"],
    ])
    await inventory_sync.stamp_availability(rows)

    assert [r["status"] for r in rows] == ["Booked", "Ready"]


async def _immediate(value):
    return value
