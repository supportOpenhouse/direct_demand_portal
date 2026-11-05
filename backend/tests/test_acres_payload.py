"""The 99acres payload mapper — pure, no network, no DB.

The first test rebuilds the one payload 99acres has actually accepted (5 Nov, E95607134),
so a mapping change that would break a live post fails here first."""
import re

from app.services.acres_payload import (
    SLOT_TAG,
    age_band,
    build_payload,
    city_id,
    lookalike_key,
)

SOC = {"latitude": 28.57, "longitude": 77.38, "possession_year": 2018}


def _prop(**over) -> dict:
    p = {
        "uid": "OHND0001", "society_name": "Mahagun Moderne", "locality": "Sector 78",
        "city": "Noida", "micro_market": "Central Noida - 76", "configuration": "2 BHK",
        "area_sqft": 1250.0, "carpet_area": None, "bathrooms": 2, "balconies": 2,
        "floor": "9", "total_floors_tower": 21, "parking": "1 Closed",
        "furnishing": "Semi-Furnished", "exit_facing": "East", "listing_price": 95.0,
        "availability_status": "Available",
    }
    p.update(over)
    return p


def test_the_test_listing_payload_is_reproduced():
    # docs/99acres-api.md "A payload that posted" — OHGD1609, DLF The Camellias
    p = _prop(society_name="DLF The Camellias", locality="Sector 42", city="Gurgaon", micro_market="Golf Course Road",
              configuration="4 BHK", bathrooms=5, balconies=3, floor="14", total_floors_tower=30,
              parking="2 Closed", furnishing="Semi-Furnished", exit_facing="North-East",
              listing_price=6480.0, area_sqft=7400.0)
    payload, problems = build_payload(p, photos=[], owntype="3", society={"latitude": 28.4513058, "longitude": 77.1006597, "possession_year": 2017}, year=2026)
    assert problems == []
    for k, v in {"Res_Com": "R", "Mode": "S", "Type": "1", "Transact_Type": "1", "City": "8",
                 "Locality": "Sector 42", "Prop_Name": "DLF The Camellias", "Latitude": "28.4513058",
                 "Longitude": "77.1006597", "Map_Source": "user_moves", "Map_Status": "MAPPED", "ZoomLevel": "16",
                 "Bedroom_Num": "4", "Bathroom_Num": "5", "Balcony_Num": "3", "Floor_Num": "14", "Total_Floor": "30",
                 "Reserved_Parking": '{"C":2}', "Furnish": "4", "Age": "2", "Owntype": "3", "Availability": "I",
                 "Price": "648000000", "Is_Price_Negotiable": "Y", "Superbuiltup_Area": "7400",
                 "Superbuiltuparea_Unit": "1", "Facing": "5"}.items():
        assert payload[k] == v, k
    assert "PhotosData" not in payload and "Carpet_Area" not in payload


def test_greater_noida_micro_markets_post_as_222_and_the_expressway_as_noida():
    assert [city_id("Noida", m) for m in ("Gr Noida West - 1", "Gr Noida West - 2", "Gaur City", "Gr Noida")] == ["222"] * 4
    assert city_id("Noida", "Gr Noida Expressway") == "7" and city_id("Noida", None) == "7"
    assert city_id("Noida", " Gaur City ") == "222"          # trimmed, as the page's filter trims
    assert (city_id("Gurgaon", None), city_id("Ghaziabad", None), city_id("Faridabad", None)) == ("8", "9", None)


def test_floor_words_and_caps():
    def f(floor, total=21):
        return build_payload(_prop(floor=floor, total_floors_tower=total), photos=[], owntype="2", society=SOC, year=2026)[0]
    assert f("Ground")["Floor_Num"] == "G" and f("Top")["Floor_Num"] == "21" and f("44", 45)["Floor_Num"] == "41"
    assert f("9", 45)["Total_Floor"] == "41"
    assert "Floor missing or not understood" in build_payload(_prop(floor=None), photos=[], owntype="2", society=SOC, year=2026)[1]


def test_parking_wordings():
    def park(w):
        return build_payload(_prop(parking=w), photos=[], owntype="2", society=SOC, year=2026)
    assert park("1 Closed")[0]["Reserved_Parking"] == '{"C":1}'
    assert park("1 Open")[0]["Reserved_Parking"] == '{"O":1}'
    assert park("1 Open + 1 Closed")[0]["Reserved_Parking"] == '{"C":1,"O":1}'
    assert park("Stilt Parking")[0]["Reserved_Parking"] == '{"C":1}'
    assert "Reserved_Parking" not in park("No Parking")[0] and "Reserved_Parking" not in park(None)[0]
    assert "Parking wording 'Basement x2' not understood" in park("Basement x2")[1]


def test_bedrooms_round_down_and_furnishing_sends_no_item_counts():
    def b(c):
        return build_payload(_prop(configuration=c), photos=[], owntype="2", society=SOC, year=2026)[0]
    assert [b(c)["Bedroom_Num"] for c in ("2.5BHK", "2.0BHK", "2 BHK + Study", "3.5 BHK")] == ["2", "2", "2", "3"]
    pay = b("2 BHK")
    assert pay["Furnish"] == "4" and not any(k.startswith("Furnish_") for k in pay)


def test_missing_answers_and_unmappable_values_are_problems():
    _, problems = build_payload(_prop(exit_facing="Up", city="Faridabad"), photos=[], owntype="9", society={}, year=2026)
    assert {"No possession year in master_societies", "Ownership not set", "No map pin in master_societies",
            "Facing 'Up' not understood", "City 'Faridabad' has no 99acres id"} <= set(problems)


def test_a_society_missing_from_master_says_so():
    _, problems = build_payload(_prop(), photos=[], owntype="2", society=None, year=2026)
    assert problems == ["Society not found in master_societies"]


def test_price_is_rupees_and_range_checked():
    pay, _ = build_payload(_prop(listing_price=52.5), photos=[], owntype="2", society=SOC, year=2026)
    assert pay["Price"] == "5250000"
    assert any("Price" in x for x in build_payload(_prop(listing_price=0.1), photos=[], owntype="2", society=SOC, year=2026)[1])


def test_carpet_area_rides_along_when_known():
    pay, _ = build_payload(_prop(carpet_area=561.83), photos=[], owntype="2", society=SOC, year=2026)
    assert (pay["Carpet_Area"], pay["Carpetarea_Unit"]) == ("562", "1")


def test_description_uses_only_allowed_punctuation():          # Review Focus 5
    pay, problems = build_payload(_prop(society_name="Gaur #12, Avenue & Co", locality="Sec-16C, Gr Noida W"),
                                  photos=[], owntype="2", society=SOC, year=2026)
    d = pay["Description"]
    assert re.fullmatch(r"[A-Za-z0-9 .;'/\\\-()]+", d) and 30 <= len(d) <= 5000 and problems == []
    assert "  " not in d


def test_description_template():
    pay, _ = build_payload(_prop(configuration="2 BHK + Study", floor="9", total_floors_tower=21), photos=[], owntype="2", society=SOC, year=2026)
    assert pay["Description"] == "2 BHK with Study semi-furnished apartment in Mahagun Moderne; Sector 78 Noida. Floor 9 of 21; East facing; 1 covered parking."


def test_photos_ordered_by_room_with_exactly_one_cover():
    shots = [{"slot_id": s, "url": f"https://res.cloudinary.com/x/{s}.jpg"} for s in
             ("balconies:1-view", "bathrooms:1", "bedrooms:2", "living_room:1", "bedrooms:1", "balconies:1")]
    pay, _ = build_payload(_prop(), photos=shots, owntype="2", society=SOC, year=2026)
    pd = pay["PhotosData"]
    assert [p["path"].rsplit("/", 1)[1] for p in pd] == ["living_room:1.jpg", "bedrooms:1.jpg", "bedrooms:2.jpg",
                                                         "bathrooms:1.jpg", "balconies:1.jpg", "balconies:1-view.jpg"]
    assert [p["cover_photo"] for p in pd].count("Y") == 1 and pd[0]["cover_photo"] == "Y"
    assert pd[0]["type"] == SLOT_TAG["living_room"]


def test_age_band_from_possession_year():
    assert [age_band(y, 2026) for y in (2026, 2025, 2022, 2017, 2016, 2005)] == ["6", "1", "1", "2", "3", "3"]
    assert age_band(None, 2026) is None and age_band(2028, 2026) is None
    assert "Possession year 2028 is in the future" in build_payload(_prop(), photos=[], owntype="2", society={**SOC, "possession_year": 2028}, year=2026)[1]


def test_lookalikes_ignore_config_spelling():
    assert lookalike_key(_prop(configuration="2.0BHK")) == lookalike_key(_prop(configuration="2 BHK"))
    assert lookalike_key(_prop(area_sqft=1250.0)) != lookalike_key(_prop(area_sqft=1251.0))


def test_a_float4_listing_price_does_not_gain_a_rupee():
    """`listing_price` is REAL: 156.6 lakh arrives as 156.60000610351562. Found on prod (OHNC1882)."""
    import struct
    as_real = struct.unpack("f", struct.pack("f", 156.6))[0]
    pay, _ = build_payload(_prop(listing_price=as_real), photos=[], owntype="2", society=SOC, year=2026)
    assert pay["Price"] == "15660000"


def test_greater_noida_listings_say_greater_noida():
    """City 222 must not be described as 'Noida' on a public listing (final review)."""
    pay, _ = build_payload(_prop(micro_market="Gaur City", locality="Sector 16C"), photos=[], owntype="2", society=SOC, year=2026)
    assert pay["City"] == "222" and "Sector 16C Greater Noida." in pay["Description"]
