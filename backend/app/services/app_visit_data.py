"""Openhouse Core's visit records → app_visit_data.

GET {CRM_BOOKING_API_BASE_URL}crm/visits/?ids=1,2,3 with X-CRM-Key — the same base URL
and key the booking client uses. The ids are every crm_visits.visit_id, sent at most
100 per request (the API's limit).

Response (verified against prod, 15 Sep):  {"visits": [...], "missingIds": [...]}
  * `missingIds` is camelCase — the announcement said missing_ids.
  * each visit is camelCase too (id, status, leadStatus, salesFeedback, demandSmFeedback…)
    and is stored verbatim; nothing is mapped until it's decided what the data is for.

Each batch commits on its own, so a failure at batch 3 keeps batches 1-2. A failed
request raises — no retry, no skip: a silently partial table would look complete.
"""
import logging
from datetime import datetime, timezone
from math import ceil

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..db import neon_engine
from ..models import AppVisitData
from .crm_booking import _client

log = logging.getLogger("app_visit_data")

BATCH = 100  # max ids per request, per the API

VISIT_IDS = text("SELECT visit_id FROM crm_visits WHERE visit_id IS NOT NULL ORDER BY visit_id")


def rows_from_response(body: dict) -> tuple[list[dict], list[dict]]:
    """(found rows, missing rows) for one API response. Found visits are kept whole."""
    now = datetime.now(timezone.utc)
    found = [{
        "visit_id": int(v["id"]),
        "found": True,
        "data": v,
        "crm_updated_at": datetime.fromisoformat(v["updatedAt"]) if v.get("updatedAt") else None,
        "fetched_at": now,
    } for v in body["visits"]]
    missing = [{"visit_id": int(i), "found": False, "fetched_at": now} for i in body["missingIds"]]
    return found, missing


async def run_app_visit_data_sync(trigger: str = "manual") -> dict:
    settings = get_settings()
    if not (settings.CRM_BOOKING_API_BASE_URL and settings.CRM_API_KEY):
        raise RuntimeError("CRM_BOOKING_API_BASE_URL / CRM_API_KEY not set")
    engine = neon_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL not configured")

    async with engine.connect() as conn:
        ids = [r[0] for r in await conn.execute(VISIT_IDS)]

    n_found = n_missing = 0
    async with _client() as client:
        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            resp = await client.get("crm/visits/", params={"ids": ",".join(map(str, chunk))})
            resp.raise_for_status()
            found, missing = rows_from_response(resp.json())

            async with engine.begin() as conn:
                if found:
                    stmt = pg_insert(AppVisitData).values(found)
                    await conn.execute(stmt.on_conflict_do_update(
                        index_elements=["visit_id"],
                        set_={c: stmt.excluded[c] for c in ("found", "data", "crm_updated_at", "fetched_at")},
                    ))
                if missing:
                    # only the flag and the time: a visit that has gone missing at Core
                    # keeps the last copy we had of it
                    stmt = pg_insert(AppVisitData).values(missing)
                    await conn.execute(stmt.on_conflict_do_update(
                        index_elements=["visit_id"],
                        set_={c: stmt.excluded[c] for c in ("found", "fetched_at")},
                    ))
            n_found += len(found)
            n_missing += len(missing)

    result = {"status": "ok", "trigger": trigger, "visit_ids": len(ids),
              "batches": ceil(len(ids) / BATCH), "found": n_found, "missing": n_missing}
    log.info("app_visit_data: %s", result)
    return result
