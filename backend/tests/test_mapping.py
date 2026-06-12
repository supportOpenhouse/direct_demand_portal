from app.services.inventory_sync import attach_photos, find_header_row, map_rows
from app.services.sheets import normalize_header, parse_price_lacs
from app.services.supply import stage_key


def test_normalize_header():
    assert normalize_header("  Asking Price (₹) ") == "asking_price"
    assert normalize_header("Society Name") == "society_name"
    assert normalize_header("super_sqft") == "super_sqft"


def test_parse_price_lacs():
    assert parse_price_lacs("₹1.2 Cr") == 120
    assert parse_price_lacs("86.5 L") == 86.5
    assert parse_price_lacs("85 Lacs") == 85
    assert parse_price_lacs("9500000") == 95
    assert parse_price_lacs("132") == 132  # bare lacs (supply demand_price style)
    assert parse_price_lacs("") is None
    assert parse_price_lacs(None) is None
    assert parse_price_lacs("call for price") is None


def test_stage_key():
    assert stage_key("AMA Req") == "ama-req"
    assert stage_key("Deal Terms") == "deal-terms"
    assert stage_key("AMA Signed") == "ama-signed"
    assert stage_key("Token Req") == "token-req"


SHEET = [
    ["Last refreshed: 2026-06-12 16:00 IST  |  137 rows", "", "", "", ""],
    ["property_name", "society_name", "city_name", "listing_price", "configuration"],
    ["Nector - 2104", "Ajnara Gen 10", "Ghaziabad", "86.5 L", "2 BHK"],
    ["", "", "", "", ""],  # blank row skipped
    ["D - 1101", "Amrapali Empire", "Ghaziabad", "74 L", "2 BHK"],
]


def test_find_header_row_skips_banner():
    assert find_header_row(SHEET) == 1


def test_map_rows():
    rows = map_rows(SHEET)
    assert len(rows) == 2
    r = rows[0]
    assert r["name"] == "Nector - 2104"
    assert r["society"] == "Ajnara Gen 10"
    assert r["city"] == "Ghaziabad"
    assert r["price_text"] == "86.5 L"
    assert r["price_lacs"] == 86.5
    assert r["configuration"] == "2 BHK"
    assert r["raw"]["listing_price"] == "86.5 L"


def test_attach_photos_joins_on_home_id():
    rows = [
        {"image_url": None, "raw": {"home_id": "247"}},
        {"image_url": None, "raw": {"home_id": "999"}},
        {"image_url": None, "raw": {}},
    ]
    photos = {"247": ["https://img/1.jpg", "https://img/2.jpg"]}
    assert attach_photos(rows, photos) == 1
    assert rows[0]["image_url"] == "https://img/1.jpg"
    assert rows[0]["raw"]["images"] == ["https://img/1.jpg", "https://img/2.jpg"]
    assert rows[1]["image_url"] is None


def test_map_rows_unknown_headers_land_in_raw():
    rows = map_rows([["weird_col", "another", "thing"], ["a", "b", "c"]])
    assert rows[0]["raw"] == {"weird_col": "a", "another": "b", "thing": "c"}
    assert rows[0]["name"] is None
