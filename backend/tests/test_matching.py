import pytest

from app.services.matching import parse_band, score_unit


def test_parse_band():
    assert parse_band("Up to ₹75 lacs") == (None, 75)
    assert parse_band("₹75 lacs – ₹1 cr") == (75, 100)
    assert parse_band("₹1.5 cr+") == (150, None)
    assert parse_band("") == (None, None)


def _req(**kw):
    base = {"city": None, "societies": [], "society_lc": set(), "micromarkets": set(),
            "config": None, "center": None, "bmin": None, "bmax": None}
    base.update(kw)
    return base


def test_score_society_is_top_tier():
    req = _req(city="Gurgaon", societies=["Sobha City"], society_lc={"sobha city"}, config="4 BHK")
    unit = {"city": "Gurgaon", "society": "Sobha City", "configuration": "4 BHK", "price_lacs": 140}
    m = score_unit(req, unit)
    assert m["tier"] == 1
    assert any("Same society" in r for r in m["reasons"])


def test_score_budget_config_city_tier3():
    req = _req(city="Gurgaon", config="3 BHK", center=85, bmin=68, bmax=102)
    unit = {"city": "Gurgaon", "society": "Other", "configuration": "3 BHK", "price_lacs": 90}
    m = score_unit(req, unit)
    assert m["tier"] == 3
    assert m["score"] > 0


def test_score_micromarket_tier2():
    req = _req(city="Gurgaon", micromarkets={"SPR 77-79"}, config="3 BHK", center=85, bmin=68, bmax=102)
    unit = {"city": "Gurgaon", "society": "X", "micro_market": "SPR 77-79", "configuration": "3 BHK", "price_lacs": 90}
    m = score_unit(req, unit)
    assert m["tier"] == 2


def test_score_city_only_is_filler_tier5():
    req = _req(city="Gurgaon", config="3 BHK", center=85, bmin=68, bmax=102)
    unit = {"city": "Gurgaon", "society": "Y", "configuration": "2 BHK", "price_lacs": 250}
    m = score_unit(req, unit)
    assert m["tier"] == 5  # same city but nothing else → still surfaced, just last
