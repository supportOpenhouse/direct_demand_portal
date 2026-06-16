"""Geocode inventory addresses → lat/lng via the Google Geocoding API.

Each unique address is geocoded once and cached in `geocode_cache`. After a sheet
sync, units missing coords are filled in (rate-limited). The visit planner needs
these coordinates to plot stops and optimize the route."""
import asyncio
import json
import logging
import urllib.parse
import urllib.request

from sqlalchemy import text

from ..config import get_settings
from ..db import neon_engine

log = logging.getLogger("geocode")

_running = False


def build_address(society: str | None, locality: str | None, city: str | None) -> str | None:
    parts = [p.strip() for p in (society, locality, city) if p and p.strip()]
    if not parts:
        return None
    return ", ".join(parts) + ", India"


def _geocode_blocking(address: str, key: str) -> tuple[float, float] | None:
    url = "https://maps.googleapis.com/maps/api/geocode/json?" + urllib.parse.urlencode(
        {"address": address, "key": key, "region": "in"}
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
    except Exception:
        log.exception("geocode request failed for %s", address)
        return None
    if data.get("status") == "OK" and data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return (loc["lat"], loc["lng"])
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        log.warning("geocode status %s for %s", data.get("status"), address)
    return None


async def geocode_inventory(limit: int = 200) -> dict:
    """Fill lat/lng for inventory units that don't have them yet. Never raises."""
    global _running
    settings = get_settings()
    engine = neon_engine()
    if engine is None or not settings.MAPS_API_KEY:
        return {"status": "not_configured", "geocoded": 0}
    if _running:
        return {"status": "busy", "geocoded": 0}
    _running = True
    geocoded = 0
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT id, society, locality, city FROM inventory_units WHERE lat IS NULL LIMIT :lim"
            ), {"lim": limit})).mappings().all()
            cache = {r[0]: (r[1], r[2]) for r in (await conn.execute(
                text("SELECT address, lat, lng FROM geocode_cache"))).all()}

        for u in rows:
            address = build_address(u["society"], u["locality"], u["city"])
            if not address:
                continue
            if address in cache:
                lat, lng = cache[address]
            else:
                coords = await asyncio.to_thread(_geocode_blocking, address, settings.MAPS_API_KEY)
                lat, lng = coords if coords else (None, None)
                cache[address] = (lat, lng)
                async with engine.begin() as conn:
                    await conn.execute(text(
                        "INSERT INTO geocode_cache (address, lat, lng) VALUES (:a,:lat,:lng) "
                        "ON CONFLICT (address) DO NOTHING"), {"a": address, "lat": lat, "lng": lng})
                await asyncio.sleep(0.05)  # be gentle on the API
            if lat is not None:
                async with engine.begin() as conn:
                    await conn.execute(text("UPDATE inventory_units SET lat=:lat, lng=:lng WHERE id=:id"),
                                       {"lat": lat, "lng": lng, "id": u["id"]})
                geocoded += 1
        if rows:
            log.info("geocoded %d/%d inventory units", geocoded, len(rows))
        return {"status": "ok", "geocoded": geocoded, "pending": len(rows)}
    except Exception:  # noqa: BLE001
        log.exception("geocode_inventory failed")
        return {"status": "error", "geocoded": geocoded}
    finally:
        _running = False
