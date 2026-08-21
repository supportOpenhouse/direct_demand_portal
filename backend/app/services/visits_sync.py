"""Visit-status sync — keeps crm_visits.status in step with the ops visits sheet.

We book on Core (POST /v1/visits/book) and store the returned Core visit id. The ops
sheet is one row per visit keyed by that same id, carrying `status`
(upcoming | completed | cancelled) plus the post-visit feedback. This job reads the
sheet and updates only the visits WE booked — everything else is ignored.

Read-only: this never writes to the sheet.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from ..config import get_settings
from ..db import neon_engine

from . import activity

log = logging.getLogger("visits_sync")

VISITS_KEY = "visits_status_sheet"
_STATUSES = {"upcoming", "completed", "cancelled"}


def _blank(v: str | None) -> str | None:
    """The sheet writes the literal 'None' for empty cells."""
    s = (v or "").strip()
    return None if s in ("", "None", "none", "NULL") else s


def _fetch_visit_rows() -> dict[int, dict]:
    """{visit_id: {status, visit_date, buyer_feedback, sales_feedback}} from the sheet."""
    from .leads_sync import _norm_header, _sheets_client

    s = get_settings()
    ws = _sheets_client().open_by_key(s.VISITS_SHEET_ID).worksheet(s.VISITS_WORKSHEET)
    values = ws.get_all_values()
    if not values:
        return {}
    header = [_norm_header(h) for h in values[0]]
    idx = {name: header.index(name) for name in header}

    def cell(row: list[str], name: str) -> str | None:
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else None

    out: dict[int, dict] = {}
    for row in values[1:]:
        raw_id = (cell(row, "id") or "").strip()
        if not raw_id.isdigit():
            continue
        status = (cell(row, "status") or "").strip().lower()
        out[int(raw_id)] = {
            "status": status if status in _STATUSES else "upcoming",
            "visit_date": _blank(cell(row, "visit_date")),
            "buyer_feedback": _blank(cell(row, "buyer_feedback")),
            "sales_feedback": _blank(cell(row, "sales_feedback")),
        }
    return out


async def run_visits_sync(trigger: str = "manual") -> dict:
    """Update the status of every visit we've booked. Never raises."""
    from .leads_sync import _write_state

    settings = get_settings()
    engine = neon_engine()
    if engine is None or not settings.leads_sheet_configured:
        detail = "Visit sync not configured (need DATABASE_URL + service account)"
        await _write_state(VISITS_KEY, "not_configured", detail, None)
        return {"status": "not_configured", "detail": detail}
    try:
        async with engine.connect() as conn:
            ours = (await conn.execute(text(
                "SELECT visit_id, lead_id, status, visit_date, buyer_feedback, sales_feedback FROM crm_visits"
            ))).mappings().all()
        if not ours:
            await _write_state(VISITS_KEY, "ok", f"no booked visits yet ({trigger})", 0)
            return {"status": "ok", "checked": 0, "updated": 0}

        sheet = await asyncio.to_thread(_fetch_visit_rows)
        updates = []
        for v in ours:
            row = sheet.get(v["visit_id"])
            if row is None:
                continue  # not on the sheet yet (freshly booked)
            if (row["status"] == v["status"] and row["visit_date"] == v["visit_date"]
                    and row["buyer_feedback"] == v["buyer_feedback"]
                    and row["sales_feedback"] == v["sales_feedback"]):
                continue  # unchanged
            updates.append({"vid": v["visit_id"], **row})

        if updates:
            # Only status MOVES are events. The sync also carries feedback and date
            # edits, and logging those as "cancelled" would be a lie; logging every
            # unchanged re-sync would bury the ones that matter.
            was = {v["visit_id"]: v["status"] for v in ours}
            lead_of = {v["visit_id"]: v.get("lead_id") for v in ours}
            moved = [u for u in updates if u["status"] != was.get(u["vid"])]

            async with engine.begin() as conn:
                await conn.execute(text(
                    "UPDATE crm_visits SET status = :status, visit_date = :visit_date, "
                    "buyer_feedback = :buyer_feedback, sales_feedback = :sales_feedback, synced_at = now() "
                    "WHERE visit_id = :vid"), updates)
                # No actor: ops changed this in the sheet, not anyone in this app.
                await activity.record(conn, [
                    activity.row_for(
                        None, entity_type="lead", entity_id=lead_of.get(u["vid"]),
                        action=f"visit_{u['status']}", field="visit_status",
                        before=was.get(u["vid"]), after=u["status"],
                        metadata={"visit_id": u["vid"], "via": "visits_sheet"})
                    for u in moved
                ])
        else:
            async with engine.begin() as conn:
                await conn.execute(text("UPDATE crm_visits SET synced_at = now()"))

        log.info("visits sync ok (%s): %d booked, %d updated", trigger, len(ours), len(updates))
        await _write_state(VISITS_KEY, "ok", f"{len(updates)} updated via {trigger}", len(updates))
        return {"status": "ok", "checked": len(ours), "updated": len(updates),
                "synced_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:  # noqa: BLE001
        log.exception("visits sync failed")
        await _write_state(VISITS_KEY, "error", str(e), None)
        return {"status": "error", "detail": str(e)}
