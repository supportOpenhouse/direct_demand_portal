"""Matching engine (HANDOVER §6.4) — pure functions, no I/O.

City is a HARD filter (applied in SQL before scoring; score_unit re-enforces it).
A unit is a real match iff: society_match OR (budget_overlap AND config_match).
Score = city(40) + society(45) + budget(25) + config(20); max 130.
The lead profile prefers confirmed-on-call data over source data (§6.1);
confirmed societies = Q4 shortlist UNION source society. A confirmed single
budget value v is matched as the band [v*(1-TOL), v*(1+TOL)].
"""
import re
from dataclasses import dataclass

BUDGET_TOLERANCE = 0.10

SCORE_CITY = 40
SCORE_SOCIETY = 45
SCORE_BUDGET = 25
SCORE_CONFIG = 20
MAX_SCORE = SCORE_CITY + SCORE_SOCIETY + SCORE_BUDGET + SCORE_CONFIG  # 130


@dataclass(frozen=True)
class LeadProfile:
    city: str | None              # normalized
    societies: frozenset[str]     # normalized
    budget_min: float | None
    budget_max: float | None
    configuration: str | None     # normalized


def normalize_text(s: str | None) -> str | None:
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip().lower() or None


def normalize_config(c: str | None) -> str | None:
    """'3 BHK' / '3bhk' / '3.5 BHK' -> '3bhk' / '3.5bhk' canonical form."""
    if not c:
        return None
    s = re.sub(r"[^0-9a-z.]", "", c.strip().lower())
    return s or None


def build_lead_profile(lead) -> LeadProfile:
    """Effective requirement: confirmed data over source data."""
    src = getattr(lead, "source_data", None)
    conf = getattr(lead, "confirmed_data", None)

    societies: set[str] = set()
    if src is not None and src.society:
        societies.add(normalize_text(src.society))
    for row in getattr(lead, "shortlist_societies", None) or []:
        n = normalize_text(row.society)
        if n:
            societies.add(n)

    city = getattr(lead, "city", None) or (src.city if src is not None else None)

    if conf is not None and conf.budget_value_lacs is not None:
        v = float(conf.budget_value_lacs)
        budget_min = v * (1 - BUDGET_TOLERANCE)
        budget_max = v * (1 + BUDGET_TOLERANCE)
    elif src is not None and (src.budget_min_lacs is not None or src.budget_max_lacs is not None):
        budget_min = src.budget_min_lacs
        budget_max = src.budget_max_lacs
    else:
        budget_min = budget_max = None

    if conf is not None and conf.configuration:
        configuration = normalize_config(conf.configuration)
    elif src is not None and src.configuration:
        configuration = normalize_config(src.configuration)
    else:
        configuration = None

    return LeadProfile(
        city=normalize_text(city),
        societies=frozenset(societies),
        budget_min=budget_min,
        budget_max=budget_max,
        configuration=configuration,
    )


def _budget_overlap(profile: LeadProfile, unit) -> bool:
    umin, umax = unit.budget_min_lacs, unit.budget_max_lacs
    if umin is None and umax is None:
        return False
    if profile.budget_min is None and profile.budget_max is None:
        return False
    lo_l = profile.budget_min if profile.budget_min is not None else float("-inf")
    hi_l = profile.budget_max if profile.budget_max is not None else float("inf")
    lo_u = umin if umin is not None else float("-inf")
    hi_u = umax if umax is not None else float("inf")
    return lo_l <= hi_u and lo_u <= hi_l  # inclusive interval overlap


def score_unit(profile: LeadProfile, unit) -> tuple[bool, int, list[str]]:
    """-> (is_match, score, matched_on). City mismatch -> excluded outright."""
    unit_city = normalize_text(getattr(unit, "city", None))

    if profile.city is not None:
        # hard filter: mirror of the SQL `unit.city == lead.city` pre-filter
        if unit_city != profile.city:
            return (False, 0, [])

    matched_on: list[str] = []
    score = 0

    if profile.city is not None and unit_city == profile.city:
        score += SCORE_CITY
        matched_on.append("city")

    unit_society = normalize_text(getattr(unit, "society", None))
    society_match = unit_society is not None and unit_society in profile.societies
    if society_match:
        score += SCORE_SOCIETY
        matched_on.append("society")

    budget_match = _budget_overlap(profile, unit)
    if budget_match:
        score += SCORE_BUDGET
        matched_on.append("budget")

    unit_config = normalize_config(getattr(unit, "configuration", None))
    config_match = profile.configuration is not None and unit_config == profile.configuration
    if config_match:
        score += SCORE_CONFIG
        matched_on.append("config")

    is_match = bool(society_match or (budget_match and config_match))
    return (is_match, score, matched_on)


def match_pct(score: int) -> int:
    return round(score / MAX_SCORE * 100)


def top_matches(profile: LeadProfile, units, limit: int = 5) -> list[tuple[object, int, list[str]]]:
    """Real matches only, ranked by score desc, truncated to `limit`."""
    scored = []
    for unit in units:
        is_match, score, matched_on = score_unit(profile, unit)
        if is_match:
            scored.append((unit, score, matched_on))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:limit]
