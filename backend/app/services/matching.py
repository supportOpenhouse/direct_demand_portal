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
import logging
import re

from sqlalchemy import text

from ..db import neon_engine, properties_engine
from .societies import society_meta
from .supply import STAGES, stage_key

log = logging.getLogger("matching")

BUDGET_TOLERANCE = 0.2  # ±20% window around a confirmed budget figure


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


async def lead_requirement(lead: dict, confirmed: dict | None) -> dict:
    """Confirmed data wins over source-captured. Enriches the lead's societies
    with their micro_markets for the geo anchor."""
    societies = []
    if confirmed and confirmed.get("shortlisted_societies"):
        societies = confirmed["shortlisted_societies"]
    elif lead.get("society"):
        societies = [lead["society"]]
    societies = [s for s in societies if s]

    micromarkets = set()
    for s in societies:
        meta = await society_meta(s)
        if meta and meta.get("micro_market"):
            micromarkets.add(meta["micro_market"])

    config = (confirmed and confirmed.get("configuration")) or lead.get("configuration")
    if confirmed and confirmed.get("budget_value_lacs"):
        b = float(confirmed["budget_value_lacs"])
        center, bmin, bmax = b, b * (1 - BUDGET_TOLERANCE), b * (1 + BUDGET_TOLERANCE)
    else:
        bmin, bmax = parse_band(lead.get("budget_band"))
        center = (bmin + bmax) / 2 if (bmin and bmax) else (bmax or bmin)
    return {
        "city": lead.get("city"),
        "societies": societies,
        "society_lc": {s.lower() for s in societies},
        "micromarkets": micromarkets,
        "config": config,
        "center": center,
        "bmin": bmin,
        "bmax": bmax,
    }


def _price_closeness(req: dict, price) -> float:
    """1.0 at the budget center, decaying to 0 at the window edge; 0 outside."""
    if price is None or req["center"] is None:
        return 0.0
    p = float(price)
    lo = req["bmin"] if req["bmin"] is not None else req["center"] * (1 - BUDGET_TOLERANCE)
    hi = req["bmax"] if req["bmax"] is not None else req["center"] * (1 + BUDGET_TOLERANCE)
    if p < lo * 0.9 or p > hi * 1.1:
        return 0.0
    span = max(hi - req["center"], req["center"] - lo, 1)
    return max(0.0, 1 - abs(p - req["center"]) / span)


def _tier(req: dict, unit: dict, society_hit: bool, mm_hit: bool, budget_ok: bool, config_hit: bool) -> int:
    """Lower = stronger. Mirrors the v2 fill-ladder priority."""
    if society_hit:
        return 1
    if mm_hit and (budget_ok or config_hit):
        return 2
    if req["city"] and unit.get("city") == req["city"] and budget_ok and config_hit:
        return 3
    if req["city"] and unit.get("city") == req["city"] and (budget_ok or config_hit):
        return 4
    return 5  # same-city filler (city filter applied upstream)


def score_unit(req: dict, unit: dict) -> dict:
    society_hit = bool(unit.get("society") and unit["society"].lower() in req["society_lc"])
    mm_hit = bool(unit.get("micro_market") and unit["micro_market"] in req["micromarkets"])
    closeness = _price_closeness(req, unit.get("price_lacs"))
    budget_ok = closeness > 0
    config_hit = bool(req["config"] and unit.get("configuration") == req["config"])
    city_hit = bool(req["city"] and unit.get("city") == req["city"])

    # continuous score (v2 weighting, adapted)
    score = (
        3.0 * society_hit
        + 2.0 * closeness
        + 1.5 * mm_hit
        + 1.0 * config_hit
        + 0.5 * city_hit
    )
    tier = _tier(req, unit, society_hit, mm_hit, budget_ok, config_hit)

    reasons = []
    if society_hit:
        reasons.append(f"Same society — {unit['society']}")
    elif mm_hit:
        reasons.append(f"Same micro-market — {unit['micro_market']}")
    elif city_hit:
        reasons.append(f"Same city — {unit['city']}")
    if config_hit:
        reasons.append(f"Same config — {unit['configuration']}")
    if budget_ok and unit.get("price_lacs") is not None:
        reasons.append(f"In budget — ₹{unit['price_lacs']}L")
    return {"tier": tier, "score": round(score, 3), "reasons": reasons[:3],
            "pct": min(60 + int(score * 8), 99)}


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
        async with engine.connect() as conn:
            res = await conn.execute(
                text(
                    "SELECT uid, society_name, locality, city, configuration, area_sqft, "
                    "demand_price, stage FROM properties WHERE stage = ANY(:stages)"
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
    else:
        base["status"] = u.get("status")
        base["image_url"] = u.get("image_url")
    return base


async def match_lead(lead: dict, confirmed: dict | None) -> dict:
    req = await lead_requirement(lead, confirmed)
    inventory = await _inventory_units()
    supply = await _supply_units()
    inv = [_shape(u, False) for u in await _rank(req, inventory)]
    sup = [_shape(u, True) for u in await _rank(req, supply)]
    return {
        "requirement": {
            "city": req["city"], "societies": req["societies"], "config": req["config"],
            "micromarkets": sorted(req["micromarkets"]), "bmin": req["bmin"], "bmax": req["bmax"],
        },
        "inventory": inv,
        "supply": sup,
    }
