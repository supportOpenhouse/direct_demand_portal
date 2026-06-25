"""Openhouse reference pricing for Supply Pipeline units.

Looks up the `oh_pricing` table (direct-inventory DB) and matches a supply unit to a
price by SOCIETY + AREA (±5 sqft) — BHK is intentionally NOT used. The society match
is exact-normalized first, then FUZZY (difflib) so spelling/format differences between
the two datasets still resolve. Produces the Match / Check-Price state shown on Supply:

  match     → society resolved + a priced area within ±5 sqft
  area_off  → society resolved, but the nearest priced area is >5 sqft away
  no_area   → the listing has no area, so it can't be area-matched
  no_match  → no OH society resolves at all
"""
import asyncio
import difflib
import logging
import re
import time

from sqlalchemy import text

from ..db import direct_inventory_engine

log = logging.getLogger("pricing")

AREA_TOLERANCE = 5      # ±5 sqft counts as a match
FUZZY_CUTOFF = 0.86     # difflib ratio needed to accept a fuzzy society match
_TTL = 600.0            # cache the (small) pricing table for 10 min
_cache: dict = {"map": None, "keys": [], "names": {}, "resolved": {}, "at": 0.0}
_lock = asyncio.Lock()


def norm_society(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


async def _load_pricing() -> None:
    """Populate _cache: {society_norm: [(area, price)]}, the key list, and display names."""
    if _cache["map"] is not None and (time.monotonic() - _cache["at"]) < _TTL:
        return
    async with _lock:
        if _cache["map"] is not None and (time.monotonic() - _cache["at"]) < _TTL:
            return
        engine = direct_inventory_engine()
        if engine is None:
            _cache.update({"map": {}, "keys": [], "names": {}, "resolved": {}, "at": time.monotonic()})
            return
        out: dict[str, list[tuple[int, int]]] = {}
        names: dict[str, str] = {}
        try:
            async with engine.connect() as conn:
                res = await conn.execute(text(
                    "SELECT society_norm, society, area_sqft, price FROM oh_pricing "
                    "WHERE society_norm IS NOT NULL AND area_sqft IS NOT NULL AND price IS NOT NULL"))
                for sn, soc, area, price in res:
                    out.setdefault(sn, []).append((int(area), int(price)))
                    names.setdefault(sn, soc or sn)
        except Exception:  # noqa: BLE001 — pricing is best-effort; never break supply
            log.exception("oh_pricing load failed")
            _cache.update({"map": {}, "keys": [], "names": {}, "resolved": {}, "at": time.monotonic()})
            return
        _cache.update({"map": out, "keys": list(out.keys()), "names": names, "resolved": {}, "at": time.monotonic()})
        log.info("oh_pricing loaded: %d societies, %d rows", len(out), sum(len(v) for v in out.values()))


def _resolve(key: str) -> tuple[str | None, bool]:
    """Resolve a normalized supply society to an oh_pricing key. Exact first, then a
    cached fuzzy best-match. Returns (resolved_key | None, was_fuzzy)."""
    if key in _cache["map"]:
        return key, False
    if key in _cache["resolved"]:
        return _cache["resolved"][key], True
    m = difflib.get_close_matches(key, _cache["keys"], n=1, cutoff=FUZZY_CUTOFF)
    resolved = m[0] if m else None
    if resolved:
        # numbers in society names (14th Avenue, Sector 49, Phase 2…) are significant —
        # never let fuzzy cross conflicting numbers (only when BOTH sides have digits)
        dq, dr = set(re.findall(r"\d+", key)), set(re.findall(r"\d+", resolved))
        if dq and dr and dq != dr:
            resolved = None
    _cache["resolved"][key] = resolved
    return resolved, True


def _price_for(society: str | None, area: float | None) -> dict:
    key = norm_society(society)
    resolved, fuzzy = _resolve(key)
    if not resolved:
        return {"price_status": "no_match", "oh_price_lacs": None, "price_reason": "no match",
                "price_tooltip": "No OH price for this society"}
    if area is None:
        return {"price_status": "no_area", "oh_price_lacs": None, "price_reason": "no area",
                "price_tooltip": "Listing has no area, so it can't be area-matched"}
    best_area, best_price = min(_cache["map"][resolved], key=lambda r: abs(r[0] - area))
    diff = abs(best_area - area)
    note = f" · society ≈ “{_cache['names'].get(resolved, resolved).title()}”" if fuzzy else ""
    if diff <= AREA_TOLERANCE:
        return {"price_status": "match", "oh_price_lacs": round(best_price / 100000, 2),
                "price_reason": None, "price_tooltip": f"Matched at {best_area} sq.ft (±{AREA_TOLERANCE} sqft){note}"}
    return {"price_status": "area_off", "oh_price_lacs": None, "price_reason": "area off",
            "price_tooltip": f"Nearest priced area is {int(round(diff))} sqft off — open card to verify{note}"}


async def enrich_supply(items: list[dict]) -> None:
    """Add price_status / oh_price_lacs / price_reason / price_tooltip to each item
    (each item must have 'society' and 'area_sqft')."""
    await _load_pricing()
    for it in items:
        it.update(_price_for(it.get("society"), it.get("area_sqft")))


async def pricing_ping() -> str:
    """'ok' | 'error' | 'not_configured' — for /v1/health."""
    engine = direct_inventory_engine()
    if engine is None:
        return "not_configured"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # noqa: BLE001
        return "error"
