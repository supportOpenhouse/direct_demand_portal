from app.services.normalize import normalize_city, normalize_config, config_bhk


def test_normalize_city_groups_noida():
    assert normalize_city("Greater Noida") == "Noida"
    assert normalize_city("Greater Noida West") == "Noida"
    assert normalize_city("Gr Noida West - 2") == "Noida"
    assert normalize_city("Noida") == "Noida"
    assert normalize_city("Gurugram") == "Gurgaon"
    assert normalize_city("gurgaon") == "Gurgaon"
    assert normalize_city("Ghaziabad") == "Ghaziabad"
    assert normalize_city("") is None
    assert normalize_city(None) is None


def test_normalize_config_merges_case_and_spacing_only():
    # case/spacing variants of the SAME config collapse together…
    assert normalize_config("2BHK") == "2 BHK"
    assert normalize_config("2 bhk") == "2 BHK"
    assert normalize_config("4BHK") == "4 BHK"
    assert normalize_config("2.5BHK") == "2.5 BHK"
    assert normalize_config("") is None


def test_normalize_config_keeps_meaningful_qualifiers():
    # …but real differences (study/servant/pooja) are NOT merged into the plain BHK
    assert normalize_config("2 BHK + Study") == "2 BHK + Study"
    assert normalize_config("2 + study") == "2 BHK + Study"  # unified with the above
    assert normalize_config("2BHK + SQ") == "2 BHK + Servant"
    assert normalize_config("3 BHK + Puja Room") == "3 BHK + Pooja"
    assert normalize_config("Studio") == "Studio"


def test_config_bhk_matches_across_qualifiers():
    # matching compares bedroom count, so 2 BHK still matches 2 BHK + Study
    assert config_bhk(normalize_config("2 BHK")) == config_bhk(normalize_config("2 BHK + Study"))
    assert config_bhk("3 BHK + Servant") == 3.0
    assert config_bhk("Studio") is None
