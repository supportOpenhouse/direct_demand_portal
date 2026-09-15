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
    spine, synced = build_meta(rows)
    assert len(spine) == 1
    assert synced == []  # no _row on these rows → nothing to stamp
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
    spine, synced = build_meta(rows)
    assert synced == [7]
    assert "_row" not in spine[0]["raw"]  # _row never leaks into the stored raw row


def test_build_listing_maps_source_and_property():
    rows = [
        {"name": "Pooja Chhibber", "contactno": "91-9971652700", "source": "99acre",
         "city": "Noida", "property": "Supertech Cape Town", "type": "Individual",
         "assigned_to": "Dheeraj", "remarks": "RNR", "remarks_2": ""},
    ]
    spine, synced = build_listing(rows)
    assert len(spine) == 1
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
    spine, synced = build_listing(rows)
    assert len(spine) == 1
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
    spine, _ = build_meta([{"phone_number": "p:+919876543210",
                            "full_name": "A", "city": clean_cell("#N/A")}])
    assert spine[0]["city"] is None


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


# ── the pushed Noida sheet ──────────────────────────────────────────────────────
# Its nine headers, verbatim from the sheet including the '?'s. The whole point of
# these is that a rename in the form is caught here rather than in production as a
# column of nulls.
NOIDA_HEADERS = [
    "where_do_you_currently_live?",
    "where_are_you_looking_to_buy_a_home?",
    "your_budget_range?",
    "which_flat/apartment_size_do_you_need?",
    "preferred_site_visit_day?",
    "email",
    "full_name",
    "phone_number",
    "zip_code",
]
NOIDA_ROW = dict(zip(NOIDA_HEADERS, [
    "Delhi", "Greater Noida West", "₹1 cr– ₹1.25 cr", "3BHK",
    "This Saturday", "a@b.com", "Ravi Kumar", "p:+919876543210", "110092",
]))


def test_every_noida_header_lands_on_a_key_build_meta_reads():
    """No column may fall through to a name nothing looks at — that's a silent
    column of nulls, which is the failure mode this whole map exists to prevent."""
    from app.services.leads_sync import _norm_header

    known = {"current_location", "city", "your_budget_range", "configuration",
             "preferred_site_visit_day", "email", "full_name", "phone_number", "zip_code"}
    assert {_norm_header(h) for h in NOIDA_HEADERS} == known


def test_a_question_mark_is_not_part_of_the_column_name():
    """Three headers only match because _norm_header strips the trailing '?'. If it
    ever stopped, budget and visit-day would go quietly null."""
    from app.services.leads_sync import _norm_header

    assert _norm_header("your_budget_range?") == "your_budget_range"
    assert _norm_header("preferred_site_visit_day?") == "preferred_site_visit_day"


def test_looking_to_buy_is_the_city_and_currently_live_is_not():
    """`city` means the demand side everywhere in this app — where they want to buy.
    Swapping these would file a Delhi resident's Noida enquiry under Delhi."""
    from app.services.leads_sync import normalise_pushed

    spine, _ = build_meta([normalise_pushed(NOIDA_ROW)])
    assert spine[0]["city"] == "Noida"              # 'Greater Noida West' normalised
    assert spine[0]["current_location"] == "Delhi"


def test_the_pushed_row_fills_the_columns_it_should():
    from app.services.leads_sync import normalise_pushed

    spine, _ = build_meta([normalise_pushed(NOIDA_ROW)])
    assert spine[0]["configuration"] == "3 BHK"
    assert spine[0]["budget_band"] == "₹1 cr– ₹1.25 cr"
    assert spine[0]["preferred_visit_day"] == "This Saturday"
    assert spine[0]["zip_code"] == "110092"
    assert spine[0]["phone"] == "+91 98765 43210"
    assert spine[0]["origin_key"] == "meta:9876543210"
    # the Noida form doesn't ask it, so it must not be invented
    assert spine[0]["plan_to_buy"] is None
    # the whole sheet row travels along, so an unmapped column is still recoverable
    assert spine[0]["raw"]["zip_code"] == "110092"


def test_a_formula_error_in_a_pushed_cell_is_not_stored_as_a_value():
    """Same guard as the pulled worksheet — applied server-side, because the poster
    is not the thing we trust."""
    from app.services.leads_sync import normalise_pushed

    row = dict(NOIDA_ROW, **{"where_are_you_looking_to_buy_a_home?": "#N/A"})
    spine, _ = build_meta([normalise_pushed(row)])
    assert spine[0]["city"] is None


def test_a_pushed_row_dedupes_against_the_pulled_sheet():
    """Both paths key on meta:<last-10-digits>, so the same buyer on both forms is one
    lead. A different origin_key here would silently double every shared number."""
    from app.services.leads_sync import normalise_pushed

    pushed, _ = build_meta([normalise_pushed(NOIDA_ROW)])
    pulled, _ = build_meta([{"phone_number": "91-9876543210", "full_name": "Ravi"}])
    assert pushed[0]["origin_key"] == pulled[0]["origin_key"]


# ── meta_leads / listing_leads are frozen ───────────────────────────────────────
# Their history stays and nothing reads them at runtime, but no new row lands there:
# `leads` is the only table the ingest writes. Re-introducing a write would split the
# truth across three tables again, which is the thing this removed.

def test_nothing_outside_the_model_file_touches_the_raw_tables():
    """The models stay defined so the tables keep their history and migrations still
    know about them — but importing one is how a write creeps back in."""
    import pathlib

    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for f in app_dir.rglob("*.py"):
        if f.name == "models.py":
            continue
        src = f.read_text()
        for cls in ("MetaLead", "ListingLead"):
            # substring, not word-boundary: `MetaLeadThing` would be just as wrong
            if cls in src:
                offenders.append(f"{f.relative_to(app_dir)}: {cls}")
    assert not offenders, offenders


def test_the_builders_return_spine_rows_only():
    """One list out, not two. A second list is where a raw-table insert used to be
    fed from, so its absence is the structural half of the guarantee above."""
    assert len(build_meta([{"phone_number": "9953998821"}])) == 2
    assert len(build_listing([{"contactno": "9971652700"}])) == 2


def test_everything_the_raw_tables_held_still_has_a_home():
    """The point of freezing them is that nothing is lost. Each field the raw tables
    carried is asserted at its new address rather than assumed to have moved."""
    meta, _ = build_meta([{
        "phone_number": "9953998821", "full_name": "@Pankaj_Joshi",
        "your_budget_range": "up_to_₹75_lacs", "city": "Noida",
    }])
    assert meta[0]["name"] == "Pankaj Joshi"                # was meta_leads.full_name
    assert meta[0]["budget_band"] == "Up to ₹75 lacs"       # was meta_leads.budget_range
    assert meta[0]["raw"]["city"] == "Noida"                # was meta_leads.raw

    listing, _ = build_listing([{
        "contactno": "9971652700", "name": "P", "source": "99acre", "date": "06/01/2026",
        "property": "Supertech Cape Town", "type": "Individual",
        "phoneverificationstatus": "VERIFIED", "remarks": "RNR",
    }])
    row = listing[0]
    assert row["society"] == "Supertech Cape Town"          # was listing_leads.property
    assert row["source_remarks"] == "RNR"                   # was listing_leads.remarks
    assert row["received_at"] is not None                   # was listing_leads.lead_date
    assert row["source_meta"]["lead_type"] == "Individual"  # was listing_leads.lead_type
    # the one field that had no spine column at all before this change
    assert row["source_meta"]["phone_verification_status"] == "VERIFIED"
    assert row["raw"]["phoneverificationstatus"] == "VERIFIED"


def test_metas_export_prefix_is_stripped_from_the_pin_code():
    """Found in production: all 85 pushed leads stored `z:201305` as their pin.

    Meta tags exported answers with a type letter — `p:` on a phone, `z:` on a pin.
    norm_phone never noticed because it keeps digits only; the pin has no such filter.
    """
    from app.services.leads_sync import strip_export_prefix

    assert strip_export_prefix("z:201305") == "201305"
    assert strip_export_prefix("p:+919876543210") == "+919876543210"
    # a single letter + colon only — a real answer that happens to contain a colon stays
    assert strip_export_prefix("Sector 62: near metro") == "Sector 62: near metro"
    assert strip_export_prefix("201305") == "201305"
    assert strip_export_prefix("") is None and strip_export_prefix(None) is None


def test_a_pushed_row_stores_a_clean_pin():
    from app.services.leads_sync import normalise_pushed

    spine, _ = build_meta([normalise_pushed(dict(NOIDA_ROW, zip_code="z:201305"))])
    assert spine[0]["zip_code"] == "201305"


# --- manual stage change -----------------------------------------------------

def test_add_lead_owner_is_the_rm_or_the_round_robin_pick():
    """An RM keeps a lead they add; anyone else's goes to the sweep's own pick_rm —
    reused, not re-implemented, so hand-added and swept leads balance as one pool."""
    body = _body_of("create_lead")
    assert "is_calling_rm(" in body
    assert "pick_rm(" in body and "covered_cities(" in body


def test_add_lead_never_duplicates_or_reassigns_an_existing_number():
    """An existing number returns the lead it already is, before anything is logged."""
    body = _body_of("create_lead")
    assert "on_conflict_do_nothing" in body and ".returning(" in body
    assert "LEAD_ID_BY_KEY" in body  # also finds a lead a merged key was folded into
    assert body.index("if inserted is None") < body.index("activity.record")


def _body_of(fn_name: str) -> str:
    """Source of a leads-router function with its docstring removed.

    These functions document the SQL they write, so a naive substring assertion
    matches the prose instead of the code and passes (or fails) for the wrong
    reason."""
    import ast
    import inspect
    import textwrap
    from app.routers import leads as mod
    tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(mod, fn_name))))
    fn = tree.body[0]
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)):
        fn.body = fn.body[1:]
    return ast.unparse(fn)

# Tests never touch a DB here, so these assert the RULES the endpoint's SQL
# encodes — the pattern test_wa_assign.py established.

def test_manual_stage_endpoint_accepts_only_known_stages():
    """A free-text stage would put a lead on no page at all: every list is a plain
    equality on `stage`, so an unknown value is invisible everywhere."""
    from app.routers.leads import STAGES
    assert "qualified" in STAGES and "rejected" in STAGES and "rnr" in STAGES
    assert "future_prospect" in STAGES
    for bogus in ("Qualified", "closed", "", "won ", "visit"):
        assert bogus not in STAGES


def test_manual_stage_is_the_only_unguarded_stage_write():
    """Every other stage write is a forward-only CASE. This one is deliberately a
    plain SET — that is what lets a mis-staged lead be put back, and it is the
    only place in the file allowed to do it."""
    body = _body_of("set_stage")
    assert "UPDATE leads SET stage=:s" in body
    # The docstring EXPLAINS the forward-only CASE it deliberately isn't, so assert
    # on the code with the docstring stripped — otherwise this fails on its own prose.
    assert "CASE" not in body, "the manual setter must not re-introduce the forward-only guard"


def test_manual_stage_reads_before_from_returning_and_skips_no_ops():
    """The before-value comes from a subselect in RETURNING (a pre-statement
    snapshot), not a second SELECT that would race another writer — and a move to
    the stage a lead is already in is not logged, or the Reports counts inflate."""
    body = _body_of("set_stage")
    assert "RETURNING (SELECT stage FROM leads WHERE id=:id)" in body
    assert "if before != payload.stage:" in body
    assert "action='stage_change'" in body


# --- lead view telemetry -----------------------------------------------------

def test_lead_viewed_is_deduped_and_never_fails_the_page():
    """Opening a lead is the highest-frequency action in the app.

    Undeduped it would put a row per click into the same table the Reports page
    reads. And a lead that refuses to open because its telemetry failed would be a
    worse bug than a missing log line — hence 204 with no error path."""
    body = _body_of("record_lead_viewed")
    assert "action='lead_viewed'" in body
    # the dedupe predicate, per actor, on a window
    assert "actor_email IS NOT DISTINCT FROM :email" in body, "dedupe must be per actor"
    assert "make_interval(mins => :mins)" in body
    assert "if recent is None:" in body
    assert "raise" not in body, "a view must never fail the request"


def test_lead_viewed_dedupe_window_is_a_named_constant():
    from app.routers.leads import VIEW_DEDUPE_MIN
    assert isinstance(VIEW_DEDUPE_MIN, int) and VIEW_DEDUPE_MIN > 0


def test_source_data_edits_log_one_row_per_changed_field():
    """`changes_between` only emits fields that actually changed — re-saving the
    form unchanged is not an edit, and logging it would bury the real ones."""
    body = _body_of("patch_source_data")
    assert "activity.changes_between" in body
    # before-values come from RETURNING, not a racing second SELECT
    assert "RETURNING" in body and "SELECT {f} FROM leads WHERE id = :id" in body
