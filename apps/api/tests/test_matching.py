"""Pure matching-engine tests (HANDOVER §6.4) — no DB needed."""
from types import SimpleNamespace

from app.services.matching import (
    BUDGET_TOLERANCE,
    MAX_SCORE,
    build_lead_profile,
    match_pct,
    score_unit,
    top_matches,
)


def make_unit(city="Gurgaon", society=None, bmin=None, bmax=None, config=None):
    return SimpleNamespace(
        city=city, society=society, budget_min_lacs=bmin, budget_max_lacs=bmax, configuration=config
    )


def make_lead(
    city="Gurgaon", society=None, bmin=None, bmax=None, config=None,
    conf_value=None, conf_config=None, shortlist=(),
):
    src = SimpleNamespace(
        city=city, society=society, budget_min_lacs=bmin, budget_max_lacs=bmax,
        configuration=config, plan_to_buy=None,
    )
    conf = None
    if conf_value is not None or conf_config is not None:
        conf = SimpleNamespace(budget_value_lacs=conf_value, configuration=conf_config, purpose="self_use")
    return SimpleNamespace(
        city=city,
        source_data=src,
        confirmed_data=conf,
        shortlist_societies=[SimpleNamespace(society=s) for s in shortlist],
    )


def profile(**kw):
    return build_lead_profile(make_lead(**kw))


def test_city_hard_filter_excludes_cross_city():
    p = profile(city="Gurgaon", society="DLF The Crest", bmin=80, bmax=100, config="3 BHK")
    unit = make_unit(city="Noida", society="DLF The Crest", bmin=80, bmax=100, config="3 BHK")
    assert score_unit(p, unit) == (False, 0, [])


def test_society_only_match_passes():
    p = profile(city="Gurgaon", society="DLF The Crest")  # no budget, no config
    unit = make_unit(city="Gurgaon", society="dlf the crest", bmin=500, bmax=600, config="5 BHK")
    is_match, score, matched_on = score_unit(p, unit)
    assert is_match is True
    assert score == 85  # city 40 + society 45
    assert matched_on == ["city", "society"]


def test_budget_plus_config_passes():
    p = profile(city="Gurgaon", society="Pioneer Park", bmin=80, bmax=100, config="3 BHK")
    unit = make_unit(city="Gurgaon", society="Some Other Society", bmin=95, bmax=120, config="3bhk")
    is_match, score, matched_on = score_unit(p, unit)
    assert is_match is True
    assert score == 85  # city 40 + budget 25 + config 20
    assert matched_on == ["city", "budget", "config"]


def test_budget_only_is_not_a_match():
    p = profile(city="Gurgaon", society="Pioneer Park", bmin=80, bmax=100, config="3 BHK")
    unit = make_unit(city="Gurgaon", society="Elsewhere", bmin=95, bmax=120, config="2 BHK")
    is_match, score, matched_on = score_unit(p, unit)
    assert is_match is False
    assert score == 65  # city 40 + budget 25 — but not a real match
    assert matched_on == ["city", "budget"]


def test_config_only_is_not_a_match():
    p = profile(city="Gurgaon", society="Pioneer Park", bmin=80, bmax=100, config="3 BHK")
    unit = make_unit(city="Gurgaon", society="Elsewhere", bmin=300, bmax=400, config="3 BHK")
    is_match, score, matched_on = score_unit(p, unit)
    assert is_match is False
    assert score == 60  # city 40 + config 20
    assert matched_on == ["city", "config"]


def test_all_four_score_130_pct_100():
    p = profile(city="Gurgaon", society="DLF The Crest", bmin=80, bmax=100, config="3.5 BHK")
    unit = make_unit(city="gurgaon", society="DLF The Crest", bmin=90, bmax=110, config="3.5bhk")
    is_match, score, matched_on = score_unit(p, unit)
    assert is_match is True
    assert score == MAX_SCORE == 130
    assert matched_on == ["city", "society", "budget", "config"]
    assert match_pct(score) == 100


def test_confirmed_preferred_over_source():
    # source band 200-300 and source config 2 BHK would NOT match this unit;
    # confirmed value 100 (±10%) and confirmed config 3.5 BHK DO.
    p = profile(
        city="Gurgaon", society="Nowhere", bmin=200, bmax=300, config="2 BHK",
        conf_value=100, conf_config="3.5 BHK",
    )
    assert p.budget_min == 100 * (1 - BUDGET_TOLERANCE)
    assert p.budget_max == 100 * (1 + BUDGET_TOLERANCE)
    unit = make_unit(city="Gurgaon", society="Elsewhere", bmin=95, bmax=105, config="3.5 BHK")
    is_match, score, matched_on = score_unit(p, unit)
    assert is_match is True
    assert matched_on == ["city", "budget", "config"]


def test_confirmed_societies_union_q4_and_source():
    p = profile(city="Gurgaon", society="Pioneer Park", conf_value=100, conf_config="3 BHK",
                shortlist=["Ireo Skyon", "M3M Golf Estate"])
    for society in ("Pioneer Park", "Ireo Skyon", "M3M Golf Estate"):
        unit = make_unit(city="Gurgaon", society=society, bmin=500, bmax=600, config="5 BHK")
        assert score_unit(p, unit)[0] is True


def test_confirmed_value_tolerance_edges():
    p = profile(city="Gurgaon", society=None, conf_value=100, conf_config="3 BHK")
    # band [90, 110]: inclusive edges
    at_upper = make_unit(city="Gurgaon", society="X", bmin=110, bmax=130, config="3 BHK")
    assert score_unit(p, at_upper)[0] is True
    above_upper = make_unit(city="Gurgaon", society="X", bmin=110.5, bmax=130, config="3 BHK")
    assert score_unit(p, above_upper)[0] is False
    at_lower = make_unit(city="Gurgaon", society="X", bmin=70, bmax=90, config="3 BHK")
    assert score_unit(p, at_lower)[0] is True
    below_lower = make_unit(city="Gurgaon", society="X", bmin=70, bmax=89.5, config="3 BHK")
    assert score_unit(p, below_lower)[0] is False


def test_top5_truncation_and_desc_order():
    p = profile(city="Gurgaon", society="Alpha", bmin=80, bmax=100, config="3 BHK",
                shortlist=["Beta", "Gamma"])
    units = [
        make_unit(city="Gurgaon", society="Alpha", bmin=90, bmax=95, config="3 BHK"),   # 130
        make_unit(city="Gurgaon", society="Beta", bmin=90, bmax=95, config="2 BHK"),    # 110
        make_unit(city="Gurgaon", society="Gamma", bmin=300, bmax=400, config="3 BHK"), # 105
        make_unit(city="Gurgaon", society="Alpha", bmin=300, bmax=400, config="2 BHK"), # 85
        make_unit(city="Gurgaon", society="Other1", bmin=90, bmax=95, config="3 BHK"),  # 85 (budget+config)
        make_unit(city="Gurgaon", society="Beta", bmin=500, bmax=600, config="5 BHK"),  # 85 (society)
        make_unit(city="Gurgaon", society="Other2", bmin=85, bmax=99, config="3bhk"),   # 85 (budget+config)
        make_unit(city="Gurgaon", society="Other3", bmin=90, bmax=95, config="2 BHK"),  # 65 — NOT a match
    ]
    results = top_matches(p, units)
    assert len(results) == 5
    scores = [score for _, score, _ in results]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 130
    assert all(score >= 85 for score in scores)
    # the non-match (budget only) never appears even though 7 matches > 5 limit
    assert all(unit is not units[-1] for unit, _, _ in results)
