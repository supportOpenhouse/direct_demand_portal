from app.services.matching import lead_requirement, parse_band, score_unit


def test_parse_band():
    assert parse_band("Up to ₹75 lacs") == (None, 75)
    assert parse_band("₹75 lacs – ₹1 cr") == (75, 100)
    assert parse_band("₹1.5 cr+") == (150, None)
    assert parse_band("") == (None, None)


def test_lead_requirement_prefers_confirmed():
    lead = {"city": "Gurgaon", "society": "X", "configuration": "2 BHK", "budget_band": "Up to ₹75 lacs"}
    confirmed = {"shortlisted_societies": ["Pivotal Devaan"], "configuration": "3 BHK", "budget_value_lacs": 85}
    req = lead_requirement(lead, confirmed)
    assert req["societies"] == ["Pivotal Devaan"]
    assert req["config"] == "3 BHK"
    assert req["bmin"] == 85 * 0.8 and req["bmax"] == 85 * 1.2


def test_lead_requirement_falls_back_to_source():
    lead = {"city": "Noida", "society": "ATS", "configuration": None, "budget_band": "Up to ₹75 lacs"}
    req = lead_requirement(lead, None)
    assert req["societies"] == ["ATS"]
    assert req["bmax"] == 75


def test_score_unit_real_match_society():
    req = {"city": "Gurgaon", "societies": ["Sobha City"], "config": "4 BHK", "bmin": None, "bmax": None}
    unit = {"city": "Gurgaon", "society": "Sobha City", "configuration": "4 BHK", "price_lacs": 140}
    score, matched = score_unit(req, unit)
    assert score > 0 and "society" in matched and "city" in matched


def test_score_unit_budget_plus_config_is_real_match():
    req = {"city": "Gurgaon", "societies": [], "config": "3 BHK", "bmin": 68, "bmax": 102}
    unit = {"city": "Gurgaon", "society": "Other", "configuration": "3 BHK", "price_lacs": 90}
    score, matched = score_unit(req, unit)
    assert score > 0 and "budget" in matched and "config" in matched


def test_score_unit_city_only_is_not_a_real_match():
    req = {"city": "Gurgaon", "societies": ["X"], "config": "3 BHK", "bmin": 68, "bmax": 102}
    unit = {"city": "Gurgaon", "society": "Y", "configuration": "2 BHK", "price_lacs": 200}
    score, _ = score_unit(req, unit)
    assert score == 0  # same city but nothing else → dropped
