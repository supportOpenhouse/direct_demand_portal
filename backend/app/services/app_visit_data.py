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
from datetime import date, datetime, timezone
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


# Core's camelCase key → our column. One mapping, used here and mirrored by
# scripts/15_app_visit_data_columns.sql, which created the columns and back-filled them;
# tests/test_app_visit_data.py fails if this and the model ever drift apart.
TEXT_COLUMNS = {
    "status": "status", "lead_status": "leadStatus", "source": "source", "city": "city",
    "society_name": "societyName", "selected_time": "selectedTime",
    "buyer_name": "buyerName", "buyer_contact": "buyerContact", "profession": "profession",
    "buyer_feedback": "buyerFeedback", "sales_feedback": "salesFeedback",
    "broker_name": "brokerName", "broker_contact": "brokerContact",
    "broker_alt_contact": "brokerAltContact", "cp_code": "cpCode",
    "company_name": "companyName", "sales_manager": "salesManager",
    "added_by": "addedBy", "first_added_by": "firstAddedBy",
    "furnishing_status": "furnishingStatus", "unit_address_line1": "unitAddressLine1",
    "unit_address_line2": "unitAddressLine2", "lead_key": "leadKey",
}
DATE_COLUMNS = {
    "selected_date": "selectedDate", "visit_date": "visitDate",
    "buyer_registration_date": "buyerRegistrationDate",
}
INT_COLUMNS = {
    "sales_manager_id": "salesManagerId", "home_id": "homeId", "floor": "floor",
    "lead_occurrence_count": "leadOccurrenceCount",
}
# Kept in the table (it is Core's record of the visit) but NEVER shown in our UI.
# Broker/CP identity and the buyer's profession are not the demand team's to work from,
# and `profession` is blank on all 336 rows anyway. Any endpoint that serves visit data
# must exclude these — tests/test_app_visit_data.py fails if one starts selecting them.
HIDDEN_FIELDS = frozenset({
    "profession", "broker_name", "broker_contact", "broker_alt_contact", "company_name",
})

# demandSmFeedback's own keys — null on a visit where the SM left no feedback
SM_COLUMNS = {
    "sm_time_spent_on_site": "timeSpentOnSite", "sm_society_amenity_tour": "societyAmenityTour",
    "sm_price_discussion": "priceDiscussion", "sm_client_queries": "clientQueries",
    "sm_closing_signal": "closingSignal", "sm_buyer_primary_concern": "buyerPrimaryConcern",
}


def _project(v: dict) -> dict:
    """One visit's JSON → the column values. `data` keeps the whole thing regardless."""
    sm = v.get("demandSmFeedback") or {}
    out: dict = {c: v.get(k) for c, k in TEXT_COLUMNS.items()}
    out.update({c: date.fromisoformat(v[k]) if v.get(k) else None for c, k in DATE_COLUMNS.items()})
    # Core sends "" — not null — for an absent id (seen on staging: salesManagerId on a
    # visit with no SM). int("") raises, which would kill the whole batch's upsert.
    out.update({c: int(v[k]) if str(v.get(k) or "").strip() else None for c, k in INT_COLUMNS.items()})
    out.update({c: sm.get(k) for c, k in SM_COLUMNS.items()})
    out["crm_created_at"] = datetime.fromisoformat(v["createdAt"]) if v.get("createdAt") else None
    out["all_feedback"] = v.get("allFeedback")
    return out


def rows_from_response(body: dict) -> tuple[list[dict], list[dict]]:
    """(found rows, missing rows) for one API response. Found visits are kept whole."""
    now = datetime.now(timezone.utc)
    found = [{
        "visit_id": int(v["id"]),
        "found": True,
        "data": v,
        "crm_updated_at": datetime.fromisoformat(v["updatedAt"]) if v.get("updatedAt") else None,
        "fetched_at": now,
        **_project(v),
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
                    # every column the row carries, so a refresh rewrites the projection
                    # too — not just `data`
                    await conn.execute(stmt.on_conflict_do_update(
                        index_elements=["visit_id"],
                        set_={c: stmt.excluded[c] for c in found[0] if c != "visit_id"},
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
