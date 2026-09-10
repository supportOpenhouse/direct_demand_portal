import re

from app.services.matching import (
    INVENTORY_FOR_MATCHING,
    INVENTORY_STATUS_SHOW,
    _budget_closeness,
    _size_closeness,
    parse_band,
    score_unit,
)


def test_parse_band():
    assert parse_band("Up to ₹75 lacs") == (None, 75)
    assert parse_band("₹75 lacs – ₹1 cr") == (75, 100)
    assert parse_band("₹1.5 cr+") == (150, None)
    assert parse_band("") == (None, None)


def _req(**kw):
    base = {"city": None, "societies": [], "society_lc": set(), "localities_lc": set(),
            "micromarkets": set(), "config": None, "size_min": None, "size_max": None,
            "bmin": None, "bmax": None}
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


def test_size_range_closeness():
    req = _req(size_min=1000, size_max=1400)
    assert _size_closeness(req, 1200) == 1.0          # inside range
    assert _size_closeness(req, 1000) == 1.0          # at min
    assert _size_closeness(req, 1400) == 1.0          # at max
    assert 0 < _size_closeness(req, 1500) < 1.0       # just over max → partial
    assert _size_closeness(req, 1700) == 0.0          # well over → no credit
    assert _size_closeness(_req(), 1200) == 0.0       # no size requirement


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


# ── CH-01: matching only offers homes that can actually be sold ─────────────────

def test_matching_filters_inventory_by_status():
    """The query had no WHERE at all — `status` was selected for display and never
    filtered on, so 26 Booked homes were being suggested to buyers."""
    src = re.sub(r"\s+", " ", str(INVENTORY_FOR_MATCHING)).strip()
    assert "WHERE status = ANY(:show)" in src


def test_inventory_filter_is_a_show_list_not_a_hide_list():
    """A status nobody has seen yet — a new value in the source sheet, a typo, NULL —
    must default to hidden. `NULL <> ALL(...)` is NULL, so a hide-list would leak a
    status-less row through; `= ANY(...)` drops it."""
    src = str(INVENTORY_FOR_MATCHING)
    assert "= ANY(" in src and "ALL(" not in src
    assert set(INVENTORY_STATUS_SHOW) == {"Available", "Ready"}
    # the two that must never be offered are absent by construction
    assert "Booked" not in INVENTORY_STATUS_SHOW and "Dead" not in INVENTORY_STATUS_SHOW
