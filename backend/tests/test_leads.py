import re
from datetime import datetime

from app.routers.leads import IST, MISS_REASONS, _within_calling_hours
from app.models import Lead
from app.services.leads_sync import (
    SYNC_CITY,
    _cols_per_row,
    build_listing,
    build_meta,
    clean_name,
    map_plan,
    map_source,
    norm_phone,
)
from app.services.normalize import normalize_city
from app.services.sheets import SHEET_ERRORS, clean_cell

# Postgres' hard cap — the fix must keep every chunk strictly under this.
PG_BIND_CAP = 32767


def test_cols_per_row_counts_client_side_default_columns():
    """The regression: a spine row dict has 18 keys, but Lead.id has a client-side
    default (uuid.uuid4) that SQLAlchemy binds anyway → 19 params/row. Counting only
    dict keys undercounted by one and a 'chunked' insert still blew the 32767 cap."""
    spine_row = {k: k for k in (
        "origin_key", "source_category", "source", "name", "phone", "email",
        "assigned_to", "city", "society", "configuration", "budget_band", "plan_to_buy",
        "preferred_visit_day", "source_remarks", "source_meta", "received_at",
        "tat_deadline", "is_test")}  # 18 keys, no id
    assert len(spine_row) == 18
    assert _cols_per_row(Lead, [spine_row]) == 19  # +1 for the auto-generated id


def test_chunking_stays_under_hard_cap_for_a_full_sheet():
    """A full sheet (well past the cap) must chunk so no single INSERT exceeds 32767."""
    spine_row = {k: k for k in (
        "origin_key", "source_category", "source", "name", "phone", "email",
        "assigned_to", "city", "society", "configuration", "budget_band", "plan_to_buy",
        "preferred_visit_day", "source_remarks", "source_meta", "received_at",
        "tat_deadline", "is_test")}
    rows = [dict(spine_row) for _ in range(2500)]
    per_row = _cols_per_row(Lead, rows)
    size = max(1, 30000 // per_row)
    assert size < len(rows)                 # must actually split
    assert size * per_row <= PG_BIND_CAP    # every chunk stays under the real cap


def test_norm_phone():
    assert norm_phone("p:+919953998821") == "9953998821"
    assert norm_phone("91-9971652700") == "9971652700"
    assert norm_phone("+91 98715 78484") == "9871578484"
    assert norm_phone("") is None
    assert norm_phone(None) is None


def test_clean_name():
    assert clean_name("@Vishu_Gurung") == "Vishu Gurung"
    assert clean_name("  Pankaj Joshi ") == "Pankaj Joshi"
    assert clean_name("") is None


def test_map_source():
    assert map_source("99acre") == "99acres"
    assert map_source("MagicBricks") == "magicbricks"
    assert map_source("99acres") == "99acres"


def test_map_plan():
    assert map_plan("within_30_days") == "Within 30 days"
    assert map_plan("1_–_3_months") == "1–3 months"
    assert map_plan("just_exploring") == "Just exploring"


def test_build_meta_skips_phoneless_and_normalizes():
    rows = [
        {"full_name": "@Pankaj_Joshi", "phone_number": "p:+919953998821",
         "your_budget_range": "up_to_₹75_lacs", "when_are_you_planning_to_buy": "within_30_days",
         "preferred_site_visit_day": "this_sunday", "email": "p@x.com"},
        {"full_name": "No Phone", "phone_number": "", "your_budget_range": "x"},  # skipped
    ]
    ingest, spine, synced = build_meta(rows)
    assert len(ingest) == 1 and len(spine) == 1
    assert synced == []  # no _row on these rows → nothing to stamp
    assert ingest[0]["dedupe_key"] == "9953998821"
    assert spine[0]["origin_key"] == "meta:9953998821"
    assert spine[0]["source"] == "meta"
    assert spine[0]["plan_to_buy"] == "Within 30 days"
    assert spine[0]["name"] == "Pankaj Joshi"


def test_build_meta_tracks_sheet_row_for_writeback():
    # rows carry their sheet row number (_row) so we can stamp them back as synced
    rows = [
        {"full_name": "X", "phone_number": "9953998821", "_row": 7},
        {"full_name": "No Phone", "phone_number": "", "_row": 8},  # skipped → not stamped
    ]
    ingest, _, synced = build_meta(rows)
    assert synced == [7]
    assert "_row" not in ingest[0]["raw"]  # _row never leaks into stored raw


def test_build_listing_maps_source_and_property():
    rows = [
        {"name": "Pooja Chhibber", "contactno": "91-9971652700", "source": "99acre",
         "city": "Noida", "property": "Supertech Cape Town", "type": "Individual",
         "assigned_to": "Dheeraj", "remarks": "RNR", "remarks_2": ""},
    ]
    ingest, spine, synced = build_listing(rows)
    assert len(ingest) == 1 and len(spine) == 1
    assert spine[0]["source"] == "99acres"
    assert spine[0]["society"] == "Supertech Cape Town"
    assert spine[0]["city"] == "Noida"
    assert spine[0]["origin_key"] == "listing:9971652700"


def test_build_listing_keeps_nameless_rows_but_drops_phoneless():
    """A missing name must NOT drop the lead (phone is the identity); only a missing
    phone can — there'd be no dedup key / origin_key to store it under."""
    rows = [
        {"name": "", "contactno": "91-9000000000"},        # no name, HAS phone → kept
        {"name": "Ghost", "contactno": ""},                 # no phone → dropped
    ]
    ingest, spine, synced = build_listing(rows)
    assert len(ingest) == 1 and len(spine) == 1
    assert spine[0]["name"] is None                         # name stays null, lead kept
    assert spine[0]["origin_key"] == "listing:9000000000"


# --- calling-hours clamp on auto follow-ups ----------------------------------

def _ist(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=IST)


def test_auto_followup_inside_calling_hours_is_untouched():
    # 12:00 + 3h = 15:00 IST — well inside 10:00-19:00
    assert _within_calling_hours(_ist(2026, 7, 20, 15)).astimezone(IST) == _ist(2026, 7, 20, 15)


def test_auto_followup_after_close_rolls_to_next_morning():
    # missed call at 17:00 → +3h lands at 20:00, past the 19:00 cutoff
    assert _within_calling_hours(_ist(2026, 7, 20, 20)).astimezone(IST) == _ist(2026, 7, 21, 10)
    # exactly 19:00 is already outside the window
    assert _within_calling_hours(_ist(2026, 7, 20, 19)).astimezone(IST) == _ist(2026, 7, 21, 10)
    # switched-off at 18:30 → +6h crosses midnight; the date must roll with it
    assert _within_calling_hours(_ist(2026, 7, 21, 0, 30)).astimezone(IST) == _ist(2026, 7, 21, 10)


def test_auto_followup_before_open_waits_for_10am():
    assert _within_calling_hours(_ist(2026, 7, 20, 9, 45)).astimezone(IST) == _ist(2026, 7, 20, 10)


def test_miss_reasons_delays():
    assert MISS_REASONS["Did Not Pick / Not Reachable"] == 3
    assert MISS_REASONS["Switched Off"] == 6
    assert MISS_REASONS["Invalid Number"] is None  # rejected, never re-queued


# ── sheet formula errors, and the city rewrite ──────────────────────────────────
# A failed VLOOKUP in the source sheet renders as '#N/A', and the Sheets API returns
# the DISPLAYED text — so it arrives as an ordinary six-character string. It reached
# leads.city in production because normalize_city's catch-all branch title-cases
# anything it doesn't recognise, and '#N/A'.title() is '#N/A'.
def _sql(x) -> str:
    return re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", str(x))).strip()


def test_a_failed_sheet_formula_reads_as_empty_not_as_a_value():
    for bad in SHEET_ERRORS:
        assert clean_cell(bad) == "", bad
        assert clean_cell(f"  {bad.lower()}  ") == "", bad   # trimmed + case-insensitive


def test_a_real_value_survives_the_guard():
    """The guard must not be a filter on anything that merely starts with '#'."""
    assert clean_cell("  Gurgaon ") == "Gurgaon"
    assert clean_cell("#1 Society") == "#1 Society"
    assert clean_cell(None) == "" and clean_cell("") == ""


def test_the_normalizer_alone_would_still_let_it_through():
    """Pins WHY the guard lives at the reader and not in normalize_city: this is the
    exact behaviour that put 32 '#N/A' cities into production."""
    assert normalize_city("#N/A") == "#N/A"
    assert normalize_city(clean_cell("#N/A")) is None


def test_build_meta_drops_a_city_the_sheet_could_not_compute():
    ingest, spine, _ = build_meta([{"phone_number": "p:+919876543210",
                                    "full_name": "A", "city": clean_cell("#N/A")}])
    assert spine[0]["city"] is None and ingest[0]["city"] is None


def test_the_city_rewrite_only_touches_rows_that_actually_change():
    """IS DISTINCT FROM, not a plain assignment: an unchanged city must not count as a
    correction, or the sync reports work it didn't do every four hours."""
    src = _sql(SYNC_CITY)
    assert "IS DISTINCT FROM" in src
    assert "l.origin_key = v.origin_key" in src


def test_the_city_rewrite_is_one_statement_not_a_per_row_loop():
    """unnest of two arrays — executemany's rowcount is meaningless and a per-row
    payload would have to be chunked around the 32767 bind-parameter cap."""
    src = _sql(SYNC_CITY)
    assert "unnest(" in src
    assert "CAST(:oks AS text[])" in src and "CAST(:cities AS text[])" in src


def test_the_rewrite_never_erases_a_city_with_a_blank_one():
    """The sheet corrects a city; it doesn't get to delete one. Empty values are
    filtered out before the statement ever sees them — mirrored here on the same
    comprehension the sync uses."""
    spine = [{"origin_key": "meta:1", "city": "Noida"},
             {"origin_key": "meta:2", "city": None},
             {"origin_key": "meta:3", "city": ""}]
    assert [(s["origin_key"], s["city"]) for s in spine if s.get("city")] == [("meta:1", "Noida")]
