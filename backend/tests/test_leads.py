from app.services.leads_sync import (
    build_listing,
    build_meta,
    clean_name,
    map_plan,
    map_source,
    norm_phone,
)


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
    ingest, spine = build_meta(rows)
    assert len(ingest) == 1 and len(spine) == 1
    assert ingest[0]["dedupe_key"] == "9953998821"
    assert spine[0]["origin_key"] == "meta:9953998821"
    assert spine[0]["source"] == "meta"
    assert spine[0]["plan_to_buy"] == "Within 30 days"
    assert spine[0]["name"] == "Pankaj Joshi"


def test_build_listing_maps_source_and_property():
    rows = [
        {"name": "Pooja Chhibber", "contactno": "91-9971652700", "source": "99acre",
         "city": "Noida", "property": "Supertech Cape Town", "type": "Individual",
         "assigned_to": "Dheeraj", "remarks": "RNR", "remarks_2": ""},
        {"name": "", "contactno": "91-9000000000"},  # skipped (no name)
    ]
    ingest, spine = build_listing(rows)
    assert len(ingest) == 1 and len(spine) == 1
    assert spine[0]["source"] == "99acres"
    assert spine[0]["society"] == "Supertech Cape Town"
    assert spine[0]["city"] == "Noida"
    assert spine[0]["origin_key"] == "listing:9971652700"
