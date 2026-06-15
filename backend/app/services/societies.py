"""master_societies (properties DB) — cached lookup + search.

Powers the lead-detail society/locality autocompletes and the micro-market geo
anchor used by the v2 matching ladder. 1.1k rows → loaded once, refreshed lazily."""
import logging

from sqlalchemy import text

from ..db import properties_engine

log = logging.getLogger("societies")

_cache: list[dict] | None = None
_by_society: dict[str, dict] | None = None


async def _load() -> list[dict]:
    global _cache, _by_society
    if _cache is not None:
        return _cache
    engine = properties_engine()
    if engine is None:
        _cache, _by_society = [], {}
        return _cache
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text(
                "SELECT city, locality, society_name, micro_market, affordable FROM master_societies"
            ))
            rows = [dict(m) for m in res.mappings()]
    except Exception:
        log.exception("master_societies load failed")
        rows = []
    _cache = rows
    _by_society = {}
    for r in rows:
        key = (r.get("society_name") or "").strip().lower()
        if key and key not in _by_society:
            _by_society[key] = r
    return _cache


async def society_meta(name: str | None) -> dict | None:
    """{city, locality, micro_market, affordable} for an exact society name."""
    if not name:
        return None
    await _load()
    return _by_society.get(name.strip().lower()) if _by_society else None


async def search_societies(q: str, limit: int = 12) -> list[dict]:
    rows = await _load()
    ql = q.strip().lower()
    if not ql:
        return []
    starts, contains = [], []
    for r in rows:
        name = (r.get("society_name") or "")
        nl = name.lower()
        if nl.startswith(ql):
            starts.append(r)
        elif ql in nl:
            contains.append(r)
    out = (starts + contains)[:limit]
    return [{"society": r["society_name"], "locality": r.get("locality"),
             "city": r.get("city"), "micro_market": r.get("micro_market")} for r in out]


async def search_localities(q: str, limit: int = 12) -> list[str]:
    rows = await _load()
    ql = q.strip().lower()
    if not ql:
        return []
    seen, starts, contains = set(), [], []
    for r in rows:
        loc = (r.get("locality") or "").strip()
        if not loc or loc.lower() in seen:
            continue
        seen.add(loc.lower())
        if loc.lower().startswith(ql):
            starts.append(loc)
        elif ql in loc.lower():
            contains.append(loc)
    return (starts + contains)[:limit]


async def search_micromarkets(q: str, limit: int = 12) -> list[dict]:
    rows = await _load()
    ql = q.strip().lower()
    if not ql:
        return []
    seen, starts, contains = set(), [], []
    for r in rows:
        mm = (r.get("micro_market") or "").strip()
        if not mm or mm.lower() in seen:
            continue
        seen.add(mm.lower())
        hit = {"micro_market": mm, "city": r.get("city")}
        if mm.lower().startswith(ql):
            starts.append(hit)
        elif ql in mm.lower():
            contains.append(hit)
    return (starts + contains)[:limit]


async def localities_in_micromarket(mm: str) -> list[str]:
    rows = await _load()
    mml = (mm or "").strip().lower()
    seen, out = set(), []
    for r in rows:
        if (r.get("micro_market") or "").strip().lower() != mml:
            continue
        loc = (r.get("locality") or "").strip()
        if loc and loc.lower() not in seen:
            seen.add(loc.lower())
            out.append(loc)
    return sorted(out)


async def societies_in_locality(loc: str) -> list[str]:
    rows = await _load()
    ll = (loc or "").strip().lower()
    seen, out = set(), []
    for r in rows:
        if (r.get("locality") or "").strip().lower() != ll:
            continue
        s = (r.get("society_name") or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return sorted(out)
