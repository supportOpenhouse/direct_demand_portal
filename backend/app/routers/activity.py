"""Reading the activity log — backs the Logs page.

Filters mirror the columns people actually ask questions with: who did it, what kind
of thing changed, which verb, over what dates, and free text. Same shape as the other
dashboard's /api/activity (docs/activity_logs/activity_log.md).

Admin-only for the whole-org list. An RM reading every other RM's reassignments and
rejections is a different product decision from an RM reading their own lead's
history — which is what the per-entity timeline below is for, and that one is open to
anyone who can already see the lead.
"""
import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from ..core.auth import current_user, require_admin
from ..db import neon_engine

log = logging.getLogger("activity")
router = APIRouter(prefix="/activity", tags=["activity"])

IST = timezone(timedelta(hours=5, minutes=30))


def activity_filters(q: str | None, action: str | None, entity_type: str | None,
                     actor: str | None, date_from: str | None,
                     date_to: str | None) -> tuple[str, dict]:
    """WHERE clause + bound params. Split out so the list, the count and the CSV
    export can never disagree about what's being shown."""
    where, params = [], {}

    if q and q.strip():
        # entity_id included so pasting a lead id finds its history — that's the most
        # common way anyone arrives at this page with a specific question
        where.append("(a.actor_email ILIKE :q OR a.actor_name ILIKE :q "
                     "OR a.action ILIKE :q OR a.field ILIKE :q "
                     "OR a.entity_id ILIKE :q OR a.before_value ILIKE :q "
                     "OR a.after_value ILIKE :q)")
        params["q"] = f"%{q.strip()}%"
    if action:
        where.append("a.action = :action")
        params["action"] = action
    if entity_type:
        where.append("a.entity_type = :entity_type")
        params["entity_type"] = entity_type
    if actor:
        where.append("lower(a.actor_email) = lower(:actor)")
        params["actor"] = actor

    # Dates are IST calendar days — the team works IST, so "the 14th" means their 14th.
    # A UTC compare would silently drop the 05:30 either side.
    if date_from:
        where.append("(a.created_at AT TIME ZONE 'Asia/Kolkata')::date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("(a.created_at AT TIME ZONE 'Asia/Kolkata')::date <= :date_to")
        params["date_to"] = date_to

    return (" WHERE " + " AND ".join(where)) if where else "", params


_SELECT = """
    SELECT a.id, a.created_at, a.actor_email, a.actor_name, a.actor_role,
           a.entity_type, a.entity_id, a.action, a.field,
           a.before_value, a.after_value, a.metadata,
           l.name AS lead_name
      FROM activity_log a
      LEFT JOIN leads l
        ON a.entity_type = 'lead'
       -- Cast the UUID to text, not the other way round. entity_id is TEXT so any key
       -- fits — 'leads_sheet' for a sync, an email for a user — and casting THAT to
       -- uuid raises on the first non-uuid row. Guarding with a regex doesn't help:
       -- AND order isn't guaranteed, so the planner can still run the cast first.
       AND l.id::text = a.entity_id
"""


def _shape(r) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime)
                else str(v) if isinstance(v, UUID) else v)
            for k, v in dict(r).items()}


@router.get("", dependencies=[Depends(require_admin)])
async def list_activity(
    q: str | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    actor: str | None = Query(None),
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    engine = neon_engine()
    if engine is None:
        return {"items": [], "total": 0}
    clause, params = activity_filters(q, action, entity_type, actor, date_from, date_to)
    async with engine.connect() as conn:
        total = (await conn.execute(text(
            f"SELECT count(*) FROM activity_log a{clause}"), params)).scalar()
        rows = (await conn.execute(text(
            f"{_SELECT}{clause} ORDER BY a.created_at DESC LIMIT :limit OFFSET :offset"),
            {**params, "limit": limit, "offset": offset})).mappings().all()
    return {"items": [_shape(r) for r in rows], "total": total}


@router.get("/filters", dependencies=[Depends(require_admin)])
async def activity_filter_options():
    """Values actually present, for the dropdowns.

    Derived rather than hardcoded: the page holds 100 rows, so building the lists from
    what's on screen would hide most of them, and a new action appears here the moment
    something writes it.
    """
    engine = neon_engine()
    if engine is None:
        return {"actions": [], "entity_types": [], "actors": []}
    async with engine.connect() as conn:
        actions = (await conn.execute(text(
            "SELECT DISTINCT action FROM activity_log ORDER BY 1"))).scalars().all()
        kinds = (await conn.execute(text(
            "SELECT DISTINCT entity_type FROM activity_log ORDER BY 1"))).scalars().all()
        actors = (await conn.execute(text(
            "SELECT DISTINCT actor_email FROM activity_log "
            "WHERE actor_email IS NOT NULL ORDER BY 1"))).scalars().all()
    return {"actions": list(actions), "entity_types": list(kinds),
            "actors": list(actors)}


@router.get("/export", dependencies=[Depends(require_admin)])
async def export_activity(
    q: str | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    actor: str | None = Query(None),
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
):
    """Same filters as the list → CSV. Capped: this is a browser download, and an
    unbounded export of an append-only table only grows."""
    engine = neon_engine()
    if engine is None:
        return StreamingResponse(io.StringIO(""), media_type="text/csv")
    clause, params = activity_filters(q, action, entity_type, actor, date_from, date_to)
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            f"{_SELECT}{clause} ORDER BY a.created_at DESC LIMIT 20000"),
            params)).mappings().all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["When (IST)", "Actor", "Role", "Entity", "Entity ID", "Lead",
                "Action", "Field", "Before", "After"])
    for r in rows:
        when = r["created_at"]
        w.writerow([
            when.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S") if when else "",
            r["actor_name"] or r["actor_email"] or "system", r["actor_role"] or "",
            r["entity_type"], r["entity_id"] or "", r["lead_name"] or "",
            r["action"], r["field"] or "", r["before_value"] or "", r["after_value"] or "",
        ])
    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="activity-log.csv"'})


@router.get("/entity/{entity_type}/{entity_id}")
async def entity_timeline(entity_type: str, entity_id: str,
                          _: dict = Depends(current_user)):
    """One entity's own history — the lead-detail timeline.

    Not admin-gated: an RM reading their own lead's history is a different thing from
    an RM reading the whole org's log. Row visibility is already decided by whether
    they can open the lead at all.
    """
    engine = neon_engine()
    if engine is None:
        return {"items": []}
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            f"{_SELECT} WHERE a.entity_type = :t AND a.entity_id = :i "
            "ORDER BY a.created_at DESC LIMIT 200"),
            {"t": entity_type, "i": entity_id})).mappings().all()
    return {"items": [_shape(r) for r in rows]}
