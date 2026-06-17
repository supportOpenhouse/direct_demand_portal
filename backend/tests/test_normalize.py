from app.services.normalize import normalize_city, normalize_config


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


def test_normalize_config_collapses_variants():
    assert normalize_config("2BHK") == "2 BHK"
    assert normalize_config("2 bhk") == "2 BHK"
    assert normalize_config("2 BHK + Study") == "2 BHK"
    assert normalize_config("2BHK + SQ") == "2 BHK"
    assert normalize_config("2.5BHK") == "2.5 BHK"
    assert normalize_config("3 BHK + Puja Room") == "3 BHK"
    assert normalize_config("4BHK") == "4 BHK"
    assert normalize_config("") is None
