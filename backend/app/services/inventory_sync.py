"""Sheet -> Neon sync. Full replace per run; the entire row is kept in `raw`
JSONB so the projection below can be tuned without re-reading the sheet.

HEADER_ALIASES: tune against the real header row once credentials exist
(see scripts in README / schema discovery)."""
import asyncio
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..db import neon_engine
from ..models import InventoryUnit, SyncState
from .sheets import fetch_sheet_values, normalize_header, parse_price_lacs

log = logging.getLogger("inventory_sync")

SYNC_KEY = "inventory_sheet"

# projected column -> accepted (normalized) sheet headers, first match wins.
# First alias of each = the real header of the live sheet (verified 2026-06-12):
# property_name, society_name, city_name, micro_market, locality_or_sector,
# listing_status, configuration, super_sqft, carpet_sqft, area_unit, exit_facing,
# balcony_view, listing_price, commission, sales_manager, photo_count, video_added,
# home_id, supply_form_uid, sales_manager_contact
HEADER_ALIASES: dict[str, list[str]] = {
    "row_key": ["home_id", "supply_form_uid", "id", "uid", "unit_id", "sr_no"],
    "name": ["property_name", "name", "project", "project_name", "unit_name", "title"],
    "society": ["society_name", "society", "building", "complex"],
    "locality": ["locality_or_sector", "micro_market", "locality", "location", "sector"],
    "city": ["city_name", "city"],
    "configuration": ["configuration", "config", "bhk", "unit_type", "type"],
    "area_sqft": ["super_sqft", "area_sqft", "area", "super_area", "carpet_sqft", "size"],
    "price_text": ["listing_price", "price", "asking_price", "demand_price", "budget"],
    "status": ["listing_status", "status", "availability"],
    "image_url": ["image_url", "image", "photo", "picture", "img"],
}

_fallback_state: dict = {"last_synced_at": None, "last_status": "not_configured", "detail": None, "row_count": None}


def find_header_row(values: list[list[str]]) -> int:
    """The sheet leads with banner rows (e.g. 'Last refreshed …'); the header is
    the first row with 3+ non-empty cells."""
    for i, row in enumerate(values[:10]):
        if sum(1 for c in row if c.strip()) >= 3:
            return i
    return 0


def map_rows(values: list[list[str]]) -> list[dict]:
    """Returns dicts shaped for inventory_units."""
    if not values:
        return []
    h_idx = find_header_row(values)
    values = values[h_idx:]
    headers = [normalize_header(h) for h in values[0]]
    col_for: dict[str, int] = {}
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in headers:
                col_for[field] = headers.index(alias)
                break
    rows = []
    for i, r in enumerate(values[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        raw = {headers[j]: r[j] for j in range(min(len(headers), len(r))) if headers[j]}
        get = lambda f: (r[col_for[f]].strip() or None) if f in col_for and col_for[f] < len(r) else None
        area = get("area_sqft")
        try:
            area_num = float(re.sub(r"[^\d.]", "", area)) if area else None
        except ValueError:
            area_num = None
        rows.append(
            {
                "row_key": get("row_key") or str(i),
                "name": get("name"),
                "society": get("society"),
                "locality": get("locality"),
                "city": get("city"),
                "configuration": get("configuration"),
                "area_sqft": area_num,
                "price_text": get("price_text"),
                "price_lacs": parse_price_lacs(get("price_text")),
                "status": get("status"),
                "image_url": get("image_url"),
                "raw": raw,
            }
        )
    return rows



async def _write_state(status: str, detail: str | None, row_count: int | None) -> None:
    _fallback_state.update(
        {"last_status": status, "detail": detail, "row_count": row_count,
         "last_synced_at": datetime.now(timezone.utc).isoformat() if status == "ok" else _fallback_state["last_synced_at"]}
    )
    engine = neon_engine()
    if engine is None:
        return
    stmt = pg_insert(SyncState).values(
        key=SYNC_KEY,
        last_synced_at=datetime.now(timezone.utc) if status == "ok" else None,
        last_status=status,
        detail=detail,
        row_count=row_count,
    )
    update_set = {"last_status": stmt.excluded.last_status, "detail": stmt.excluded.detail, "row_count": stmt.excluded.row_count}
    if status == "ok":
        update_set["last_synced_at"] = stmt.excluded.last_synced_at
    stmt = stmt.on_conflict_do_update(index_elements=[SyncState.key], set_=update_set)
    try:
        async with engine.begin() as conn:
            await conn.execute(stmt)
    except Exception:
        log.exception("failed to persist sync_state")


def fetch_photo_map() -> dict[str, list[str]]:
    """Blocking. home_id -> image URLs, from the OH photos API (one call, all homes)."""
    import json as _json
    import urllib.request

    url = get_settings().PHOTOS_API_URL
    if not url:
        return {}
    with urllib.request.urlopen(url, timeout=30) as r:
        data = _json.load(r)
    out: dict[str, list[str]] = {}
    for h in data.get("homePhoto", []):
        images = [i for i in (h.get("images") or []) if i]
        if images and h.get("homeId") is not None:
            out[str(h["homeId"])] = images
    return out


def attach_photos(rows: list[dict], photos: dict[str, list[str]]) -> int:
    """Sets image_url (first photo) by joining raw.home_id; returns match count."""
    matched = 0
    for row in rows:
        hid = str(row["raw"].get("home_id") or "").strip()
        if hid and hid in photos:
            row["image_url"] = photos[hid][0]
            row["raw"]["images"] = photos[hid]
            matched += 1
    return matched


async def run_sync(trigger: str = "manual") -> dict:
    """Returns {status, rows?, detail?}. Never raises."""
    settings = get_settings()
    if not settings.sheets_configured:
        detail = "Sheets sync not configured — set GOOGLE_SERVICE_ACCOUNT_JSON and SHEET_ID"
        await _write_state("not_configured", detail, None)
        return {"status": "not_configured", "detail": detail}
    if neon_engine() is None:
        detail = "Neon not configured — set DATABASE_URL"
        await _write_state("not_configured", detail, None)
        return {"status": "not_configured", "detail": detail}
    try:
        values = await asyncio.to_thread(fetch_sheet_values)
        rows = map_rows(values)
        try:
            photos = await asyncio.to_thread(fetch_photo_map)
            matched = attach_photos(rows, photos)
            log.info("photos joined: %d/%d rows", matched, len(rows))
        except Exception:  # photos are best-effort; never block the sync
            log.exception("photo fetch failed — syncing without images")
        engine = neon_engine()
        async with engine.begin() as conn:
            await conn.execute(delete(InventoryUnit))
            if rows:
                await conn.execute(InventoryUnit.__table__.insert(), rows)
        await _write_state("ok", f"{len(rows)} rows via {trigger}", len(rows))
        log.info("inventory sync ok (%s): %d rows", trigger, len(rows))
        return {"status": "ok", "rows": len(rows)}
    except Exception as e:  # noqa: BLE001 — sync must never crash the app
        log.exception("inventory sync failed (%s)", trigger)
        await _write_state("error", str(e), None)
        return {"status": "error", "detail": str(e)}


async def read_state() -> dict:
    engine = neon_engine()
    if engine is None:
        return dict(_fallback_state)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text("SELECT last_synced_at, last_status, detail, row_count FROM sync_state WHERE key = :k"),
                {"k": SYNC_KEY},
            )
            row = res.mappings().first()
        if row is None:
            return dict(_fallback_state)
        return {
            "last_synced_at": row["last_synced_at"].isoformat() if row["last_synced_at"] else None,
            "last_status": row["last_status"],
            "detail": row["detail"],
            "row_count": row["row_count"],
        }
    except Exception as e:  # table missing, connection error…
        return {"last_synced_at": None, "last_status": "error", "detail": str(e), "row_count": None}
