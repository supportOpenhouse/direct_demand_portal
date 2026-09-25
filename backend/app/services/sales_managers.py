"""Openhouse Core's sales managers → sales_manager_list.

GET {CRM_BOOKING_API_BASE_URL}crm/sales-managers/ with X-CRM-Key — the same client and
key as booking. Measured on staging, 25 Sep (the doc they sent is wrong on both counts):
  * the keys are camelCase — {"salesManagers": [{id, name, mobile, cityId, cityName,
    isActive}]}, not sales_managers / city_id / city_name / is_active
  * an unknown `city_id` returns 200 with an empty list, not 400 "city not valid"
Only ACTIVE managers are listed.

A refresh is ONE transaction: upsert everyone listed, then mark every stored manager the
response did NOT list as inactive. Nobody is ever deleted — an old visit still names them.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import neon_engine
from ..models import SalesManagerList
from .crm_booking import _client, _err_text

log = logging.getLogger("sales_managers")

# Managers the latest response didn't list have left the active roster. Only rows still
# marked active are touched, so `fetched_at` keeps the last time each was actually seen.
DEACTIVATE_MISSING = text("""
    UPDATE sales_manager_list SET is_active = false
     WHERE is_active AND NOT (id = ANY(:seen))
""")


def rows_from_response(body: dict, now: datetime) -> list[dict]:
    """The API's managers → table rows. Reads the camelCase keys Core really sends."""
    return [{
        "id": int(m["id"]),
        "name": m["name"],
        "mobile": m.get("mobile") or None,
        "city_id": m.get("cityId"),
        "city_name": m.get("cityName") or None,
        "is_active": bool(m.get("isActive", True)),
        "data": m,
        "fetched_at": now,
    } for m in body["salesManagers"]]


async def fetch_sales_managers() -> list[dict]:
    """Every active manager, as rows. Raises on a failed request — a refresh must not
    run on a partial or empty answer it can't trust."""
    async with _client() as client:
        r = await client.get("crm/sales-managers/")
    if r.status_code != 200:
        raise RuntimeError(f"crm/sales-managers/ → {r.status_code}: {_err_text(r)}")
    return rows_from_response(r.json(), datetime.now(timezone.utc))


async def refresh_sales_managers(apply: bool = True) -> dict:
    """Fetch the roster and store it. `apply=False` fetches and counts, writes nothing."""
    rows = await fetch_sales_managers()
    # An empty roster is a broken answer, not "everyone quit": acting on it would mark
    # every stored manager inactive in one go. Refuse, and let the next run try again.
    if not rows:
        raise RuntimeError("crm/sales-managers/ returned no managers — refusing to deactivate everyone")

    engine = neon_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL not configured")
    seen = [r["id"] for r in rows]
    async with engine.connect() as conn:
        # read-only here: a dry run must not create the table it is only looking at
        exists = (await conn.execute(text("SELECT to_regclass('public.sales_manager_list')"))).scalar()
        stored = ({r[0]: r[1] for r in await conn.execute(text("SELECT id, is_active FROM sales_manager_list"))}
                  if exists else {})
    result = {
        "applied": apply, "listed": len(rows),
        "new": len(set(seen) - set(stored)),
        "updated": len(set(seen) & set(stored)),
        "to_deactivate": sum(1 for i, active in stored.items() if active and i not in set(seen)),
        "by_city": _by_city(rows),
    }
    if not apply:
        return result

    async with engine.begin() as conn:
        # DDL is transactional in Postgres: if the upsert fails, the new table goes too
        await conn.run_sync(lambda c: SalesManagerList.__table__.create(c, checkfirst=True))
        stmt = pg_insert(SalesManagerList).values(rows)
        await conn.execute(stmt.on_conflict_do_update(
            index_elements=["id"],
            # first_seen_at is never rewritten; everything the API says is
            set_={c: stmt.excluded[c] for c in rows[0] if c != "id"},
        ))
        await conn.execute(DEACTIVATE_MISSING, {"seen": seen})
    log.info("sales managers: %s", result)
    return result


def _by_city(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r["city_name"] or "—"] = out.get(r["city_name"] or "—", 0) + 1
    return out
