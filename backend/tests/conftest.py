"""Session-wide guard: no test can reach a real database.

backend/.env points DATABASE_URL at PRODUCTION (the properties and direct-inventory URLs are production too), and
the settings read it. Every test that touches the DB patches the engine — but one that forgets would write to
prod. An environment variable outranks the .env file in pydantic-settings, so blanking them here, before anything
builds the (lru_cached) settings, leaves every engine unconfigured: neon_engine() returns None for the whole run.
This module is imported by pytest before any test module."""
import os

for _var in ("DATABASE_URL", "PROPERTIES_DATABASE_URL", "DIRECT_INVENTORY_DB_URL"):
    os.environ[_var] = ""
