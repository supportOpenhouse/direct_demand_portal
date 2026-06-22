"""Supply Pipeline: live read-only queries against the external properties DB.

Column set is introspected once and cached; missing columns degrade to nulls.
Contact/owner columns are never returned (no-auth frontend this phase)."""
import json
import logging
import re

from sqlalchemy import text

from ..db import properties_engine

log = logging.getLogger("supply")

# The Supply Pipeline shows live units from cp_inventory_status.supply_status (joined
# on uid), not the stale properties.stage. We show ALL statuses EXCEPT the
# dead / rejected / cancelled / duplicate ones below.
SUPPLY_STATUS_HIDE = [
    "Duplicacy", "Dead - Sold", "OH Rejected", "Dead - Not Interested",
    "Visit Cancelled", "Seller Rejected", "Cancelled Post Token", "Dead - Legal",
]

# raw supply_status → displayed stage (Hold + Price High fold into Future Prospect)
STATUS_DISPLAY = {"Hold": "Future Prospect", "Price High": "Future Prospect"}


def display_status(raw: str | None) -> str | None:
    return STATUS_DISPLAY.get(raw, raw) if raw else raw

# the Direct Demand priority flag we add to the external properties table
PRIORITY_COLUMN = "direct_demand_priority"

# columns we will SELECT if they exist (superset; intersected with reality)
CANDIDATE_COLUMNS = [
    "uid", "id", "stage", "society_name", "society", "locality", "city",
    "configuration", "area_sqft", "demand_price", "offer_price",
    "tower_no", "unit_no", "floor", "additional_images", "image_url",
    "is_high_priority", "is_dead", "status_override", "source", "created_at",
    PRIORITY_COLUMN,
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
    stage = display_status(row.get("supply_status"))
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
        "priority": bool(row.get(PRIORITY_COLUMN)),
        "raw": raw,
    }


async def ensure_priority_column() -> None:
    """Add the Direct Demand priority flag to the external properties table.
    Idempotent; needs ALTER permission on that DB."""
    engine = properties_engine()
    if engine is None:
        return
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                f"ALTER TABLE properties ADD COLUMN IF NOT EXISTS {PRIORITY_COLUMN} BOOLEAN NOT NULL DEFAULT false"))
        global _columns_cache
        _columns_cache = None  # force re-introspect so the new column is picked up
        log.info("ensured properties.%s column", PRIORITY_COLUMN)
    except Exception:
        log.exception("could not add %s to properties (need ALTER permission?)", PRIORITY_COLUMN)


async def set_priority(uid: str, value: bool) -> dict:
    """Set/unset Direct Demand priority on a property. Returns {status}."""
    engine = properties_engine()
    if engine is None:
        return {"status": "not_configured"}
    try:
        async with engine.begin() as conn:
            res = await conn.execute(
                text(f"UPDATE properties SET {PRIORITY_COLUMN} = :v WHERE uid = :uid"),
                {"v": value, "uid": uid})
        if res.rowcount == 0:
            return {"status": "not_found"}
        return {"status": "ok", "priority": value}
    except Exception as e:  # noqa: BLE001
        log.exception("set_priority failed for %s", uid)
        return {"status": "error", "detail": str(e)}


async def fetch_supply() -> dict:
    """Returns {status, detail, items}. Never raises."""
    engine = properties_engine()
    if engine is None:
        return {"status": "not_configured", "detail": "Set PROPERTIES_DATABASE_URL", "items": []}
    try:
        cols = await _get_columns(engine)
        # join the live status table; the displayed stage = cp_inventory_status.supply_status
        select_cols = [f"p.{c}" for c in CANDIDATE_COLUMNS if c in cols and c != "stage"]
        sql = text(
            f"SELECT {', '.join(select_cols)}, s.supply_status "
            "FROM properties p JOIN cp_inventory_status s ON s.uid = p.uid "
            "WHERE s.supply_status <> ALL(:hide) AND s.supply_status <> ''"
        )
        async with engine.connect() as conn:
            res = await conn.execute(sql, {"hide": SUPPLY_STATUS_HIDE})
            rows = [dict(m) for m in res.mappings()]
        return {"status": "ok", "detail": None, "items": [_row_to_item(r) for r in rows]}
    except Exception as e:  # noqa: BLE001
        log.exception("supply fetch failed")
        return {"status": "unavailable", "detail": str(e), "items": []}
