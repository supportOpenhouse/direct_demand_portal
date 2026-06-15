from app.services.matching import _budget_closeness, _size_closeness, parse_band, score_unit


def test_parse_band():
    assert parse_band("Up to ₹75 lacs") == (None, 75)
    assert parse_band("₹75 lacs – ₹1 cr") == (75, 100)
    assert parse_band("₹1.5 cr+") == (150, None)
    assert parse_band("") == (None, None)


def _req(**kw):
    base = {"city": None, "societies": [], "society_lc": set(), "localities_lc": set(),
            "micromarkets": set(), "config": None, "size": None, "bmin": None, "bmax": None}
    base.update(kw)
    return base


def test_budget_range_in_and_above():
    req = _req(bmin=70, bmax=90)
    assert _budget_closeness(req, 80) == (1.0, True)          # inside range
    assert _budget_closeness(req, 90) == (1.0, True)          # at max
    c, ok = _budget_closeness(req, 95); assert ok and 0.5 < c < 1.0   # +5L over → allowed, decayed
    c, ok = _budget_closeness(req, 100); assert ok and c == 0.5       # +10L over → edge
    assert _budget_closeness(req, 105) == (0.0, False)        # beyond +10L → out
    c, ok = _budget_closeness(req, 60); assert ok             # cheaper than min → acceptable


def test_size_closeness():
    req = _req(size=1000)
    assert _size_closeness(req, 1000) == 1.0
    assert _size_closeness(req, 1100) == 1.0          # within ±15%
    assert 0 < _size_closeness(req, 1250) < 1.0       # 25% off → partial credit
    assert _size_closeness(req, 1400) == 0.0          # >30% off → no credit
    assert _size_closeness(_req(), 1000) == 0.0       # no target size


def test_budget_is_the_gate():
    # in-budget unit (tier ≤4) beats an out-of-budget same-society unit (tier 5)
    req = _req(city="Gurgaon", societies=["X"], society_lc={"x"}, config="3 BHK", bmin=70, bmax=90)
    in_budget = {"city": "Gurgaon", "society": "Y", "configuration": "3 BHK", "price_lacs": 85}
    out_budget_society = {"city": "Gurgaon", "society": "X", "configuration": "3 BHK", "price_lacs": 200}
    assert score_unit(req, in_budget)["tier"] < score_unit(req, out_budget_society)["tier"]


def test_in_budget_reason_present():
    req = _req(city="Gurgaon", bmin=70, bmax=90)
    m = score_unit(req, {"city": "Gurgaon", "society": "Z", "configuration": "2 BHK", "price_lacs": 80})
    assert any("In budget" in r for r in m["reasons"])
