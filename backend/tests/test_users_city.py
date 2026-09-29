"""Settings → Edit user → "Takes new leads for".

users.city drives the lead sweep's city routing (services/lead_assign.py). Until 29 Sep it
could only be set by hand in the database; these pin the edit path.
"""
import inspect

from app.routers import users
from app.services.normalize import normalize_city


def test_the_list_sends_each_users_cities():
    src = inspect.getsource(users.list_users)
    assert "city" in src.split("FROM users", 1)[0], "the SELECT must read users.city"
    assert '"city": u["city"] or []' in src, "never null to the client — [] means none"


def test_patch_accepts_cities_and_writes_the_column():
    assert "city" in users.UserUpdate.model_fields
    src = inspect.getsource(users.update_user)
    assert '"city")' in src, "city must be in the fields the UPDATE writes"
    # the before-row feeds changes_between; without city in it every save would log
    # the cities as changed from nothing
    assert "city FROM users WHERE id = :id" in src


def test_cities_are_stored_in_the_spelling_leads_use():
    """The sweep compares users.city to leads.city case-insensitively, but a variant
    spelling ("gurugram") would never match a lead the sync stored as "Gurgaon"."""
    assert normalize_city("gurugram") == "Gurgaon"
    assert normalize_city(" noida ") == "Noida"
    assert "normalize_city(x) for x in payload.city" in inspect.getsource(users.update_user)
