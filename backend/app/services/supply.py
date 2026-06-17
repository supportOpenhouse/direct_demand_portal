"""Supply Pipeline: live read-only queries against the external properties DB.

Column set is introspected once and cached; missing columns degrade to nulls.
Contact/owner columns are never returned (no-auth frontend this phase)."""
import json
import logging
import re

from sqlalchemy import text

from ..db import properties_engine

log = logging.getLogger("supply")

STAGES = ["AMA Req", "Deal Terms", "Draft", "AMA Signed", "Visited", "Token Req"]

# business rule: 'Draft' is not a real stage — those units are at token, so they
# display under 'Token Req' (DB filter above still matches the raw 'Draft' rows)
DISPLAY_STAGE = {"Draft": "Token Req"}

# columns we will SELECT if they exist (superset; intersected with reality)
CANDIDATE_COLUMNS = [
    "uid", "id", "stage", "society_name", "society", "locality", "city",
    "configuration", "area_sqft", "demand_price", "offer_price",
    "tower_no", "unit_no", "floor", "additional_images", "image_url",
    "is_high_priority", "is_dead", "status_override", "source", "created_at",
]

# never expose these even if present in raw
PRIVATE_COLUMNS = {"contact_no", "first_name", "last_name", "owner_broker_name", "phone", "email"}

_columns_cache: list[str] | None = None


def stage_key(stage: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (stage or "").lower()).strip("-")


def _first_image(val) -> str | None:
    if not val:
        return None
    if isinstance(val, list):
        return str(val[0]) if val else None
    s = str(val).strip()
    if s.startswith("["):
        try:
            arr = json.loads(s)
            return str(arr[0]) if arr else None
        except (json.JSONDecodeError, IndexError):
            return None
    return s.split(",")[0].strip() or None


async def _get_columns(engine) -> list[str]:
    global _columns_cache
    if _columns_cache is None:
        async with engine.connect() as conn:
            res = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'properties'")
            )
            _columns_cache = [r[0] for r in res]
            try:
                stages = await conn.execute(text("SELECT DISTINCT stage FROM properties LIMIT 50"))
                log.info("properties.stage distinct values: %s", sorted([str(s[0]) for s in stages]))
            except Exception:
                log.warning("could not read DISTINCT stage")
    return _columns_cache


def _row_to_item(row: dict) -> dict:
    from .normalize import normalize_city, normalize_config

    cfg = normalize_config(row.get("configuration"))
    society = (row.get("society_name") or row.get("society") or "").strip() or None
    name = " · ".join(x for x in (cfg, society) if x) or society or str(row.get("uid") or row.get("id"))
    from .sheets import parse_price_lacs

    price_text = row.get("demand_price")
    price_text = str(price_text).strip() if price_text not in (None, "") else None
    raw = {k: (str(v) if v is not None else None) for k, v in row.items() if k not in PRIVATE_COLUMNS}
    stage = DISPLAY_STAGE.get(row.get("stage"), row.get("stage"))
    return {
        "id": str(row.get("uid") or row.get("id")),
        "name": name,
        "society": society,
        "locality": row.get("locality"),
        "city": normalize_city(row.get("city")),
        "stage": stage,
        "stage_key": stage_key(stage or ""),
        "configuration": cfg,
        "area_sqft": float(row["area_sqft"]) if row.get("area_sqft") not in (None, "") else None,
        "price_text": price_text,
        "price_lacs": parse_price_lacs(price_text),
        "image_url": _first_image(row.get("additional_images") or row.get("image_url")),
        "raw": raw,
    }


async def fetch_supply() -> dict:
    """Returns {status, detail, items}. Never raises."""
    engine = properties_engine()
    if engine is None:
        return {"status": "not_configured", "detail": "Set PROPERTIES_DATABASE_URL", "items": []}
    try:
        cols = await _get_columns(engine)
        if "stage" not in cols:
            return {"status": "unavailable", "detail": "properties.stage column not found", "items": []}
        select_cols = [c for c in CANDIDATE_COLUMNS if c in cols]
        sql = text(
            f"SELECT {', '.join(select_cols)} FROM properties "
            f"WHERE stage = ANY(:stages)" + (" AND (is_dead IS NULL OR is_dead = false)" if "is_dead" in cols else "")
        )
        async with engine.connect() as conn:
            res = await conn.execute(sql, {"stages": STAGES})
            rows = [dict(m) for m in res.mappings()]
        return {"status": "ok", "detail": None, "items": [_row_to_item(r) for r in rows]}
    except Exception as e:  # noqa: BLE001
        log.exception("supply fetch failed")
        return {"status": "unavailable", "detail": str(e), "items": []}
