"""Lead → unit matching, ported from the prototype's scoreUnit/matchScore.

City is a hard filter (when the lead has one). Score = city(40) + society(45) +
budget(25) + config(20). A unit is a *real* match only if society matches OR
(budget overlaps AND config matches) — otherwise it is dropped, so the lists stay
relevant instead of padding with same-city noise. Top 5 each from live inventory
(Neon) and the supply pipeline (external DB)."""
import logging
import re

from sqlalchemy import text

from ..db import neon_engine, properties_engine
from .supply import STAGES, stage_key

log = logging.getLogger("matching")


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


def lead_requirement(lead: dict, confirmed: dict | None) -> dict:
    """Confirmed data wins over source-captured, mirroring the prototype."""
    societies = []
    if confirmed and confirmed.get("shortlisted_societies"):
        societies = confirmed["shortlisted_societies"]
    elif lead.get("society"):
        societies = [lead["society"]]
    config = (confirmed and confirmed.get("configuration")) or lead.get("configuration")
    if confirmed and confirmed.get("budget_value_lacs"):
        b = float(confirmed["budget_value_lacs"])
        bmin, bmax = b * 0.8, b * 1.2  # ±20% window around the confirmed figure
    else:
        bmin, bmax = parse_band(lead.get("budget_band"))
    return {
        "city": lead.get("city"),
        "societies": [s for s in societies if s],
        "config": config,
        "bmin": bmin,
        "bmax": bmax,
    }


def _budget_ok(req: dict, price_lacs) -> bool:
    if price_lacs is None or (req["bmin"] is None and req["bmax"] is None):
        return False
    p = float(price_lacs)
    if req["bmin"] is not None and p < req["bmin"] * 0.9:
        return False
    if req["bmax"] is not None and p > req["bmax"] * 1.1:
        return False
    return True


def score_unit(req: dict, unit: dict) -> tuple[int, list[str]]:
    matched = []
    score = 0
    if req["city"] and unit.get("city") == req["city"]:
        score += 40
        matched.append("city")
    society_hit = unit.get("society") and unit["society"] in req["societies"]
    if society_hit:
        score += 45
        matched.append("society")
    budget_hit = _budget_ok(req, unit.get("price_lacs"))
    if budget_hit:
        score += 25
        matched.append("budget")
    config_hit = req["config"] and unit.get("configuration") == req["config"]
    if config_hit:
        score += 20
        matched.append("config")
    real = society_hit or (budget_hit and config_hit)
    return (score if real else 0, matched)


def _rank(req: dict, units: list[dict], limit: int = 5) -> list[dict]:
    # hard city filter when the lead has a city
    pool = [u for u in units if not req["city"] or u.get("city") == req["city"]]
    scored = []
    for u in pool:
        s, matched = score_unit(req, u)
        if s > 0:
            scored.append({**u, "score": min(s + 5, 99), "matched_on": matched})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


async def _inventory_units() -> list[dict]:
    engine = neon_engine()
    if engine is None:
        return []
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT id, name, society, locality, city, configuration, area_sqft, "
            "price_text, price_lacs, status, image_url FROM inventory_units"
        ))
        return [dict(m) for m in res.mappings()]


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
    return out


def _inv_item(u: dict) -> dict:
    return {
        "id": u["id"], "name": u.get("name"), "society": u.get("society"), "locality": u.get("locality"),
        "city": u.get("city"), "configuration": u.get("configuration"),
        "area_sqft": float(u["area_sqft"]) if u.get("area_sqft") is not None else None,
        "price_text": u.get("price_text"),
        "price_lacs": float(u["price_lacs"]) if u.get("price_lacs") is not None else None,
        "status": u.get("status"), "image_url": u.get("image_url"),
        "score": u["score"], "matched_on": u["matched_on"],
    }


async def match_lead(lead: dict, confirmed: dict | None) -> dict:
    req = lead_requirement(lead, confirmed)
    inventory = await _inventory_units()
    supply = await _supply_units()
    inv_ranked = [_inv_item(u) for u in _rank(req, inventory)]
    sup_ranked = _rank(req, supply)
    return {
        "requirement": req,
        "inventory": inv_ranked,
        "supply": [{**u, "price_lacs": (float(u["price_lacs"]) if u.get("price_lacs") is not None else None)} for u in sup_ranked],
    }
