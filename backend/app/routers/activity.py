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
import json
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from ..core.auth import current_user, require_admin
from ..db import neon_engine

log = logging.getLogger("activity")
router = APIRouter(prefix="/activity", tags=["activity"])

IST = timezone(timedelta(hours=5, minutes=30))


def activity_filters(q: str | None, action: str | None, entity_type: str | None,
                     actor: str | None, date_from: date | None,
                     date_to: date | None) -> tuple[str, dict]:
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


_COLUMNS = """
    SELECT a.id, a.created_at, a.actor_email, a.actor_name, a.actor_role,
           a.entity_type, a.entity_id, a.action, a.field,
           a.before_value, a.after_value, a.metadata,
           l.name AS lead_name"""
_FROM = """
      FROM activity_log a
      LEFT JOIN leads l
        ON a.entity_type = 'lead'
       -- Cast the UUID to text, not the other way round. entity_id is TEXT so any key
       -- fits — 'leads_sheet' for a sync, an email for a user — and casting THAT to
       -- uuid raises on the first non-uuid row. Guarding with a regex doesn't help:
       -- AND order isn't guaranteed, so the planner can still run the cast first.
       AND l.id::text = a.entity_id
"""
_SELECT = _COLUMNS + _FROM

# "Status at the time": the lead's stage when the event happened. The last stage_change
# at or before it says what the stage BECAME; failing that, the first stage_change after
# it says what the stage WAS (its before_value); a lead with no stage_change at all is
# still in its current stage. Both lookups ride ix_activity_entity (entity_type,
# entity_id, created_at) — 20,000 rows in 0.19s on prod, 24 Sep.
# ⚠️ Stage logging began 19 Aug. An event before a lead's first logged change reads that
# change's `before`, which is right; an event on a lead never logged reads its CURRENT
# stage, which is only a guess for old events.
STAGE_AT_TIME = """
           CASE WHEN a.entity_type = 'lead' THEN COALESCE(
             (SELECT s.after_value FROM activity_log s
               WHERE s.entity_type = 'lead' AND s.entity_id = a.entity_id
                 AND s.action = 'stage_change' AND s.created_at <= a.created_at
               ORDER BY s.created_at DESC LIMIT 1),
             (SELECT s.before_value FROM activity_log s
               WHERE s.entity_type = 'lead' AND s.entity_id = a.entity_id
                 AND s.action = 'stage_change' AND s.created_at > a.created_at
               ORDER BY s.created_at ASC LIMIT 1),
             l.stage) END AS stage_at_time"""

# The CSV adds lead columns the table never shows. They are NOT in _SELECT: the list
# endpoint serves the Activity Logs table, and a column in its JSON reaches every browser
# that opens the page whether or not the table draws it. The phone is for the export only.
_EXPORT_SELECT = (_COLUMNS + """,
           l.phone AS lead_phone, l.stage AS lead_stage_now, l.source AS lead_source,
           l.city AS lead_city, l.assigned_to AS lead_owner,""" + STAGE_AT_TIME + _FROM)

# Every column the CSV can carry, in the order it writes them: (key, header, on by
# default). The Download dialog offers exactly these — lib/api.ts mirrors the list and
# tests/test_activity_export.py fails if the two drift. A request naming no fields gets
# the defaults, which is what an older frontend (no dialog) still receives.
EXPORT_FIELDS: list[tuple[str, str, bool]] = [
    ("when", "When (IST)", True),
    ("actor", "Actor", True),
    ("role", "Role", True),
    ("entity", "Entity", True),
    ("entity_id", "Entity ID", True),
    ("lead", "Lead", True),
    ("lead_phone", "Lead phone", True),
    ("status_at_time", "Status at the time", True),
    ("action", "Action", True),
    ("field", "Field", True),
    ("before", "Before", True),
    ("after", "After", True),
    ("status_now", "Current status", False),
    ("source", "Source", False),
    ("city", "City", False),
    ("owner", "Assigned RM", False),
    ("details", "Details (JSON)", False),
]


def _export_value(key: str, r) -> str:
    """One cell. Kept beside EXPORT_FIELDS so a new field is one entry in each."""
    if key == "when":
        return r["created_at"].astimezone(IST).strftime("%Y-%m-%d %H:%M:%S") if r["created_at"] else ""
    if key == "actor":
        return r["actor_name"] or r["actor_email"] or "system"
    if key == "details":
        return json.dumps(r["metadata"], ensure_ascii=False, default=str) if r["metadata"] else ""
    col = {"role": "actor_role", "entity": "entity_type", "entity_id": "entity_id",
           "lead": "lead_name", "lead_phone": "lead_phone", "status_at_time": "stage_at_time",
           "action": "action", "field": "field", "before": "before_value",
           "after": "after_value", "status_now": "lead_stage_now", "source": "lead_source",
           "city": "lead_city", "owner": "lead_owner"}[key]
    v = r[col]
    return "" if v is None else str(v)


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
    date_from: date | None = Query(None, alias="from"),  # a date, not str: asyncpg won't
    date_to: date | None = Query(None, alias="to"),      # bind a str against ::date (500)
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
    date_from: date | None = Query(None, alias="from"),  # a date, not str: asyncpg won't
    date_to: date | None = Query(None, alias="to"),      # bind a str against ::date (500)
    fields: list[str] | None = Query(None),
):
    """Same filters as the list → CSV. Capped: this is a browser download, and an
    unbounded export of an append-only table only grows.

    `fields` picks the columns (repeated param). Written in EXPORT_FIELDS order whatever
    order they were sent in, so two people's exports line up column for column."""
    known = [k for k, _h, _d in EXPORT_FIELDS]
    if fields:
        unknown = sorted(set(fields) - set(known))
        if unknown:
            raise HTTPException(status_code=422, detail=f"unknown export fields: {unknown}")
        chosen = [k for k in known if k in set(fields)]
    else:
        chosen = [k for k, _h, on in EXPORT_FIELDS if on]
    engine = neon_engine()
    if engine is None:
        return StreamingResponse(io.StringIO(""), media_type="text/csv")
    clause, params = activity_filters(q, action, entity_type, actor, date_from, date_to)
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            f"{_EXPORT_SELECT}{clause} ORDER BY a.created_at DESC LIMIT 20000"),
            params)).mappings().all()

    buf = io.StringIO()
    w = csv.writer(buf)
    header = dict((k, h) for k, h, _d in EXPORT_FIELDS)
    w.writerow([header[k] for k in chosen])
    for r in rows:
        w.writerow([_export_value(k, r) for k in chosen])
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
