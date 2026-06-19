"""Lead → unit matching (v2). Adapted from the seller-flow "Similar Properties v2"
ladder to buyer-lead matching.

Improvements over v1 (the old hard-gate scorer):
- Tier fill-ladder: a stronger tier always beats a weaker one; we rank by a
  continuous score only *within* a tier, so we surface up to N matches instead of
  dropping everything that isn't a society/budget+config hit.
- Continuous closeness on budget (1.0 at exact → 0 at the window edge) instead of
  a binary in/out.
- micro_market (from master_societies) as the geo anchor between society and city.
- match_reasons per unit for the UI.

City is the only hard filter, and only when the lead actually has a city.
"""
import asyncio
import logging
import re
import time

from sqlalchemy import text

from ..db import neon_engine, properties_engine
from .normalize import normalize_city, normalize_config, config_bhk
from .societies import society_meta
from .supply import STAGES, stage_key

log = logging.getLogger("matching")

BUDGET_TOLERANCE = 0.2  # ±20% window around a confirmed budget figure

# in-memory unit cache so live preview (one call per keystroke) never re-hits the
# DBs — units barely change during an editing session. Scoring is pure in-memory.
_UNITS_TTL = 90  # seconds
_cache: dict = {"inventory": None, "supply": None, "at": 0.0}
_lock = asyncio.Lock()


def parse_band(band: str | None) -> tuple[float | None, float | None]:
    """'Up to ₹75 lacs' -> (None,75); '₹75 lacs – ₹1 cr' -> (75,100); '₹1.5 cr+' -> (150,None)."""
    if not band:
        return (None, None)
    s = band.lower().replace(",", "")
    nums = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(cr|crore|lac|lakh|l)?", s):
        v = float(m.group(1))
        unit = m.group(2) or ""
        if unit.startswith("cr") or unit == "crore":
            v *= 100
        nums.append(v)
    if not nums:
        return (None, None)
    if "up to" in s or "under" in s or "below" in s:
        return (None, max(nums))
    if "+" in s or "above" in s or "over" in s:
        return (min(nums), None)
    if len(nums) >= 2:
        return (min(nums), max(nums))
    return (nums[0], nums[0])


BUDGET_TOP_TOLERANCE = 10  # show units up to ₹10L above the buyer's max
SIZE_TOLERANCE = 0.15      # ±15% on sqft = full size match


async def build_requirement(
    city: str | None,
    societies: list[str] | None,
    localities: list[str] | None,
    micromarkets: list[str] | None,
    config: str | None,
    size_min_sqft: float | None,
    size_max_sqft: float | None,
    budget_min_lacs: float | None,
    budget_max_lacs: float | None,
    budget_band: str | None,
) -> dict:
    """Shared requirement builder for saved-lead matching and live preview.
    Budget and size are both RANGES; budget is the top priority."""
    societies = [s for s in (societies or []) if s]
    localities = [l for l in (localities or []) if l]
    mms = {m for m in (micromarkets or []) if m}
    for s in societies:  # enrich with the societies' own micro-markets
        meta = await society_meta(s)
        if meta and meta.get("micro_market"):
            mms.add(meta["micro_market"])

    bmin, bmax = budget_min_lacs, budget_max_lacs
    if bmin is None and bmax is None:
        bmin, bmax = parse_band(budget_band)
    return {
        "city": normalize_city(city),
        "societies": societies,
        "society_lc": {s.lower() for s in societies},
        "localities_lc": {l.lower() for l in localities},
        "micromarkets": mms,
        "config": normalize_config(config),
        "bhk": config_bhk(config),  # bedroom count — matches "2 BHK" against "2 BHK + Study"
        "size_min": float(size_min_sqft) if size_min_sqft else None,
        "size_max": float(size_max_sqft) if size_max_sqft else None,
        "bmin": float(bmin) if bmin is not None else None,
        "bmax": float(bmax) if bmax is not None else None,
    }


async def lead_requirement(lead: dict, confirmed: dict | None) -> dict:
    """Confirmed data wins over source-captured."""
    c = confirmed or {}
    societies = c.get("shortlisted_societies") or ([lead["society"]] if lead.get("society") else [])
    bmin, bmax = c.get("budget_min_lacs"), c.get("budget_max_lacs")
    if bmin is None and bmax is None and c.get("budget_value_lacs"):  # legacy single value
        v = float(c["budget_value_lacs"])
        bmin, bmax = v * 0.9, v
    smin, smax = c.get("size_min_sqft"), c.get("size_max_sqft")
    if smin is None and smax is None and c.get("size_sqft"):  # legacy single value
        smin = smax = c["size_sqft"]
    return await build_requirement(
        lead.get("city"), societies, c.get("preferred_localities"), c.get("preferred_micromarkets"),
        c.get("configuration") or lead.get("configuration"), smin, smax,
        bmin, bmax, lead.get("budget_band"),
    )


def _budget_closeness(req: dict, price) -> tuple[float, bool]:
    """Budget is the top signal. In-range → 1.0; up to ₹10L above max decays 1.0→0.5;
    cheaper than min is fine (down to a floor). Returns (closeness, in_budget)."""
    if price is None or (req["bmin"] is None and req["bmax"] is None):
        return (0.0, False)
    p = float(price)
    lo = req["bmin"]
    hi = req["bmax"] if req["bmax"] is not None else p  # no max → only a floor
    if lo is not None and hi is not None and lo <= p <= hi:
        return (1.0, True)
    if hi is not None and p > hi:                       # above max — allow +10L
        over = p - hi
        if over <= BUDGET_TOP_TOLERANCE:
            return (max(0.5, 1 - 0.5 * over / BUDGET_TOP_TOLERANCE), True)
        return (0.0, False)
    if lo is not None and p < lo:                       # cheaper than min — acceptable
        if p >= lo * 0.7:
            return (max(0.75, 1 - (lo - p) / lo), True)
        return (0.0, False)
    return (1.0, True)


def _size_closeness(req: dict, area) -> float:
    """Range version: 1.0 inside [min,max]; decays to 0 within ±15% of the bound."""
    lo, hi = req.get("size_min"), req.get("size_max")
    if area is None or (lo is None and hi is None):
        return 0.0
    a = float(area)
    if (lo is None or a >= lo) and (hi is None or a <= hi):
        return 1.0
    if hi is not None and a > hi:
        tol = hi * SIZE_TOLERANCE
        return max(0.0, 1 - (a - hi) / tol) if tol else 0.0
    if lo is not None and a < lo:
        tol = lo * SIZE_TOLERANCE
        return max(0.0, 1 - (lo - a) / tol) if tol else 0.0
    return 0.0


def _tier(req: dict, unit: dict, in_budget: bool, society_hit: bool, geo_hit: bool, fit_hit: bool) -> int:
    """Budget is the gate (highest priority): in-budget units always rank above
    out-of-budget ones. Within budget: society > area > config/size > just-budget."""
    if in_budget:
        if society_hit:
            return 1
        if geo_hit:
            return 2
        if fit_hit:  # config and/or size
            return 3
        return 4
    return 5  # out of budget — filler (same city)


def score_unit(req: dict, unit: dict) -> dict:
    society_hit = bool(unit.get("society") and unit["society"].lower() in req["society_lc"])
    mm_hit = bool(unit.get("micro_market") and unit["micro_market"] in req["micromarkets"])
    locality_hit = bool(unit.get("locality") and unit["locality"].lower() in req.get("localities_lc", set()))
    geo_hit = mm_hit or locality_hit
    budget_close, in_budget = _budget_closeness(req, unit.get("price_lacs"))
    size_close = _size_closeness(req, unit.get("area_sqft"))
    config_hit = bool(req.get("bhk") is not None and config_bhk(unit.get("configuration")) == req["bhk"])
    city_hit = bool(req["city"] and unit.get("city") == req["city"])

    # budget is the dominant weight, then BHK/size/society/area
    score = (
        3.5 * budget_close
        + 2.0 * society_hit
        + 1.5 * config_hit
        + 1.5 * size_close
        + 1.2 * mm_hit
        + 1.0 * locality_hit
        + 0.5 * city_hit
    )
    tier = _tier(req, unit, in_budget, society_hit, geo_hit, config_hit or size_close > 0)

    reasons = []
    if in_budget and unit.get("price_lacs") is not None:
        reasons.append(f"In budget — ₹{unit['price_lacs']}L")
    if society_hit:
        reasons.append(f"Same society — {unit['society']}")
    elif mm_hit:
        reasons.append(f"Same micro-market — {unit['micro_market']}")
    elif locality_hit:
        reasons.append(f"Same locality — {unit['locality']}")
    elif city_hit:
        reasons.append(f"Same city — {unit['city']}")
    if config_hit:
        reasons.append(f"Same config — {unit['configuration']}")
    if size_close > 0 and unit.get("area_sqft"):
        reasons.append(f"Size fit — {int(unit['area_sqft'])} sq.ft")
    return {"tier": tier, "score": round(score, 3), "reasons": reasons[:4],
            "pct": min(58 + int(score * 8), 99)}


async def _rank(req: dict, units: list[dict], limit: int = 5) -> list[dict]:
    pool = [u for u in units if not req["city"] or u.get("city") == req["city"]]
    scored = []
    for u in pool:
        m = score_unit(req, u)
        scored.append({**u, **m})
    # tier first (a Tier-1 always beats a Tier-3), then score desc within tier
    scored.sort(key=lambda x: (x["tier"], -x["score"]))
    return scored[:limit]


async def _enrich_micromarket(units: list[dict]) -> None:
    for u in units:
        if not u.get("micro_market") and u.get("society"):
            meta = await society_meta(u["society"])
            if meta:
                u["micro_market"] = meta.get("micro_market")


async def _inventory_units() -> list[dict]:
    engine = neon_engine()
    if engine is None:
        return []
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT id, name, society, locality, city, configuration, area_sqft, "
            "price_text, price_lacs, status, image_url FROM inventory_units"
        ))
        units = [dict(m) for m in res.mappings()]
    for u in units:
        u["price_lacs"] = float(u["price_lacs"]) if u.get("price_lacs") is not None else None
        u["id"] = str(u["id"])
    await _enrich_micromarket(units)
    return units


async def _supply_units() -> list[dict]:
    engine = properties_engine()
    if engine is None:
        return []
    try:
        from .supply import PRIORITY_COLUMN

        async with engine.connect() as conn:
            has_priority = (await conn.execute(text(
                "SELECT 1 FROM information_schema.columns WHERE table_name='properties' AND column_name=:c"),
                {"c": PRIORITY_COLUMN})).first() is not None
            pcol = f", {PRIORITY_COLUMN}" if has_priority else ""
            res = await conn.execute(
                text(
                    "SELECT uid, society_name, locality, city, configuration, area_sqft, "
                    f"demand_price, stage{pcol} FROM properties WHERE stage = ANY(:stages)"
                ),
                {"stages": STAGES},
            )
            rows = [dict(m) for m in res.mappings()]
    except Exception:
        log.exception("supply units fetch failed")
        return []
    from .sheets import parse_price_lacs

    out = []
    for r in rows:
        out.append({
            "id": str(r.get("uid")),
            "name": " · ".join(x for x in [r.get("configuration"), r.get("society_name")] if x) or str(r.get("uid")),
            "society": r.get("society_name"),
            "locality": r.get("locality"),
            "city": r.get("city"),
            "configuration": r.get("configuration"),
            "area_sqft": float(r["area_sqft"]) if r.get("area_sqft") not in (None, "") else None,
            "price_text": str(r["demand_price"]).strip() if r.get("demand_price") not in (None, "") else None,
            "price_lacs": parse_price_lacs(r.get("demand_price")),
            "stage": r.get("stage"),
            "stage_key": stage_key(r.get("stage") or ""),
            "priority": bool(r.get("direct_demand_priority")),
        })
    await _enrich_micromarket(out)
    return out


def _shape(u: dict, supply: bool) -> dict:
    base = {
        "id": u["id"], "name": u.get("name"), "society": u.get("society"), "locality": u.get("locality"),
        "city": u.get("city"), "micro_market": u.get("micro_market"), "configuration": u.get("configuration"),
        "area_sqft": float(u["area_sqft"]) if u.get("area_sqft") is not None else None,
        "price_text": u.get("price_text"),
        "price_lacs": float(u["price_lacs"]) if u.get("price_lacs") is not None else None,
        "score": u["pct"], "tier": u["tier"], "matched_on": u["reasons"],
    }
    if supply:
        base["stage"] = u.get("stage")
        base["stage_key"] = u.get("stage_key")
        base["priority"] = bool(u.get("priority"))
    else:
        base["status"] = u.get("status")
        base["image_url"] = u.get("image_url")
    return base


def invalidate_units_cache() -> None:
    """Force the next match to reload units (e.g. after a priority change)."""
    _cache["at"] = 0.0


async def _load_units(force: bool = False) -> tuple[list[dict], list[dict]]:
    """Inventory + supply units, cached in-memory for _UNITS_TTL so live preview
    is a pure in-memory score (no DB round-trip per keystroke)."""
    fresh = (time.monotonic() - _cache["at"]) < _UNITS_TTL
    if not force and fresh and _cache["inventory"] is not None:
        return _cache["inventory"], _cache["supply"]
    async with _lock:
        if not force and (time.monotonic() - _cache["at"]) < _UNITS_TTL and _cache["inventory"] is not None:
            return _cache["inventory"], _cache["supply"]
        inventory, supply = await asyncio.gather(_inventory_units(), _supply_units())
        _cache.update({"inventory": inventory, "supply": supply, "at": time.monotonic()})
        log.info("units cache refreshed: %d inventory, %d supply", len(inventory), len(supply))
        return inventory, supply


async def _match(req: dict) -> dict:
    inventory, supply = await _load_units()
    inv = [_shape(u, False) for u in await _rank(req, inventory)]
    sup = [_shape(u, True) for u in await _rank(req, supply)]
    return {
        "requirement": {
            "city": req["city"], "societies": req["societies"], "config": req["config"],
            "size_min": req.get("size_min"), "size_max": req.get("size_max"),
            "localities": sorted(req.get("localities_lc", set())),
            "micromarkets": sorted(req["micromarkets"]), "bmin": req["bmin"], "bmax": req["bmax"],
        },
        "inventory": inv,
        "supply": sup,
    }


async def match_lead(lead: dict, confirmed: dict | None) -> dict:
    return await _match(await lead_requirement(lead, confirmed))


async def match_preview(payload: dict) -> dict:
    """Live preview from in-progress form fields (no save needed)."""
    req = await build_requirement(
        payload.get("city"), payload.get("societies"), payload.get("localities"),
        payload.get("micromarkets"), payload.get("configuration"),
        payload.get("size_min_sqft"), payload.get("size_max_sqft"),
        payload.get("budget_min_lacs"), payload.get("budget_max_lacs"), payload.get("budget_band"),
    )
    return await _match(req)
