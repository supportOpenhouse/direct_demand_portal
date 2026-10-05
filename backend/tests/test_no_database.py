"""tests/conftest.py blanks every database URL before the settings load (G-14): backend/.env is PRODUCTION, and a
test that forgot to patch the engine must find no database rather than prod."""
from app.config import get_settings
from app.db import direct_inventory_engine, neon_engine, properties_engine


def test_no_test_can_reach_a_real_database():
    s = get_settings()
    assert (s.DATABASE_URL, s.PROPERTIES_DATABASE_URL, s.DIRECT_INVENTORY_DB_URL) == ("", "", "")
    assert neon_engine() is None and properties_engine() is None and direct_inventory_engine() is None
