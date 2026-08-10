"""Live availability for inventory units.

The sheet's listing_status is what supply typed when the unit was listed, and it goes
stale the moment something is booked. demand_details.availability_status is the live
truth, joined on the sheet's supply_form_uid -> demand_details.uid.

Applied in two places, deliberately:
  * the sheet sync writes it into inventory_units.status, so everything reading that
    table — the matching engine especially — sees real availability rather than
    recommending a flat that sold last week;
  * /v1/inventory re-applies it per request, because "is this still sellable" is
    exactly the thing that must not be up to a sync interval stale.

Fallback beats the join in importance: an unmatched unit keeps its sheet status. A
third of rows have no match, and a blank tag is worse than a slightly stale one.
"""
import logging

from sqlalchemy import text

from ..db import properties_engine

log = logging.getLogger("availability")

# demand_details lives in the properties database, so this can never be a SQL join
# with inventory_units — it's a second read and an in-Python merge.
#
# The ids come from a spreadsheet anyone in ops can edit and they reach another
# database, so they travel bound, never inlined.
_AVAILABILITY = text(
    "SELECT uid, availability_status FROM demand_details WHERE uid = ANY(:uids)"
)


def uids_of(items: list[dict]) -> list[str]:
    """The supply_form_uids present on these rows, blanks dropped."""
    out = []
    for item in items:
        uid = str((item.get("raw") or {}).get("supply_form_uid") or "").strip()
        if uid:
            out.append(uid)
    return out


def apply_availability(items: list[dict], statuses: dict[str, str]) -> int:
    """Overwrite each unit's sheet status with its live one. Returns the match count.

    Anything unmatched keeps the sheet status, and so does a blank live value — an
    empty availability_status is not an answer, and a unit with no tag at all reads as
    a bug rather than as missing data.
    """
    matched = 0
    for item in items:
        uid = str((item.get("raw") or {}).get("supply_form_uid") or "").strip()
        if not uid:
            continue
        live = (statuses.get(uid) or "").strip()
        if not live:
            continue
        item["status"] = live
        matched += 1
    return matched


async def live_statuses(uids: list[str]) -> dict[str, str]:
    """uid -> availability_status.

    Best-effort: an unreachable properties database returns nothing and every unit
    falls back to its sheet status, which is the same path an unmatched uid already
    takes. Availability must never fail the page or the sync.
    """
    engine = properties_engine()
    if engine is None or not uids:
        return {}
    try:
        async with engine.connect() as conn:
            return dict((await conn.execute(_AVAILABILITY, {"uids": uids})).all())
    except Exception:  # noqa: BLE001
        log.exception("availability lookup failed — falling back to sheet status")
        return {}


async def resolve(items: list[dict]) -> int:
    """Look up and apply in one call. Returns how many statuses were replaced."""
    return apply_availability(items, await live_statuses(uids_of(items)))
