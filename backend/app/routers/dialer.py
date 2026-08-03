"""Auto-dialer campaigns — build a queue from a rule tree, then let the scheduler
work it. Admin-only: a campaign rings other people's phones.

The dialling itself lives in services/dialer.py; this is the control surface.
"""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from ..core.auth import require_admin
from ..db import neon_engine
from ..services.dialer import (
    FIELDS, OPS, aliases_for, assign_owners, compile_rules, count_matching, materialize,
)

log = logging.getLogger("dialer")
router = APIRouter(prefix="/dialer", tags=["dialer"])

# multi-select fields whose options come from whatever is actually in the leads table
_OPTION_COLUMNS = {"society": "society", "city": "city", "source": "source",
                   "stage": "stage", "assigned_to": "assigned_to"}


def _engine():
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    return engine


class Rules(BaseModel):
    rules: dict
    # the pool matters to the count only under 'assigned', where a lead nobody in it
    # owns is never dialled
    strategy: str = "round_robin"
    rms: list[str] = []


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rules: dict
    rms: list[str] = []
    strategy: str = "round_robin"
    gap_seconds: int = Field(default=0, ge=0, le=3600)
    window_start: str = "10:00"
    window_end: str = "19:00"
    max_attempts: int = Field(default=1, ge=1, le=10)
    cooldown_minutes: int = Field(default=360, ge=0, le=10080)
    start: bool = True  # create and immediately begin dialling


@router.get("/fields")
async def dialer_fields(_: dict = Depends(require_admin)):
    """The condition builder's vocabulary — the same whitelist the compiler enforces,
    plus the distinct values currently present for each multi-select field."""
    engine = _engine()
    options: dict[str, list[str]] = {}
    async with engine.connect() as conn:
        for key, col in _OPTION_COLUMNS.items():
            rows = (await conn.execute(text(
                f"SELECT DISTINCT {col} AS v FROM leads "
                f"WHERE {col} IS NOT NULL AND btrim({col}) <> '' ORDER BY 1 LIMIT 300"
            ))).mappings().all()
            options[key] = [r["v"] for r in rows]
        rms = (await conn.execute(text(
            "SELECT email, name, assignment_name, phone FROM users "
            "WHERE active ORDER BY name NULLS LAST, email"
        ))).mappings().all()
    return {
        "fields": [
            {"key": k, "label": v["label"], "kind": v["kind"],
             "ops": sorted(OPS[v["kind"]]), "options": options.get(k, [])}
            for k, v in FIELDS.items()
        ],
        "rms": [
            {"email": r["email"], "name": r["name"] or r["assignment_name"] or r["email"],
             "has_phone": bool(r["phone"])}
            for r in rms
        ],
    }


@router.post("/preview")
async def dialer_preview(payload: Rules, _: dict = Depends(require_admin)):
    """Live match count for the rule tree, as the user edits it.

    Under 'assigned' it counts only what the chosen RMs actually own — that's the
    number of calls the campaign will place. With no RMs chosen yet the pool is
    undefined, so it falls back to the plain rule count.
    """
    engine = _engine()
    aliases: list[str] = []
    if payload.strategy == "assigned" and payload.rms:
        wanted = {e.lower() for e in payload.rms}
        async with engine.connect() as conn:
            users = (await conn.execute(text(
                "SELECT email, name, assignment_name FROM users WHERE active"))).mappings().all()
        for u in users:
            if u["email"].lower() in wanted:
                aliases += aliases_for(u["name"], u["assignment_name"])
        if not aliases:
            return {"count": 0, "scoped": True}  # chosen RMs answer to no name in the data
    try:
        return {"count": await count_matching(payload.rules, aliases), "scoped": bool(aliases)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/campaigns")
async def list_campaigns(_: dict = Depends(require_admin)):
    engine = _engine()
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT c.id, c.name, c.status, c.strategy, c.rms, c.created_at, c.started_at,
                   count(q.id) FILTER (WHERE q.status = 'pending')            AS pending,
                   count(q.id) FILTER (WHERE q.status = 'dialing')            AS live,
                   count(q.id) FILTER (WHERE q.status IN ('done','failed'))   AS completed,
                   count(q.id)                                                AS total
              FROM dial_campaigns c LEFT JOIN dial_queue q ON q.campaign_id = c.id
             GROUP BY c.id ORDER BY c.created_at DESC LIMIT 50
        """))).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.post("/campaigns", status_code=201)
async def create_campaign(payload: CampaignIn, user: dict = Depends(require_admin)):
    engine = _engine()
    if payload.strategy not in ("assigned", "round_robin", "least_load"):
        raise HTTPException(status_code=400, detail=f"unknown strategy {payload.strategy!r}")
    try:
        compile_rules(payload.rules)  # fail before we write anything
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not payload.rms:
        raise HTTPException(status_code=400, detail="pick at least one RM to do the calling")

    async with engine.begin() as conn:
        users = (await conn.execute(text(
            "SELECT email, name, assignment_name FROM users WHERE active"))).mappings().all()
        known = {u["email"].lower(): u for u in users}
        unknown = [e for e in payload.rms if e.lower() not in known]
        if unknown:
            raise HTTPException(status_code=400, detail=f"not an active user: {unknown[0]}")

        cid = (await conn.execute(text("""
            INSERT INTO dial_campaigns
                   (id, name, rules, rms, strategy, gap_seconds, window_start, window_end,
                    max_attempts, cooldown_minutes, status, created_by, started_at)
            VALUES (gen_random_uuid(), :name, CAST(:rules AS jsonb), CAST(:rms AS jsonb),
                    :strategy, :gap, :ws, :we, :att, :cool, :status, :by,
                    CASE WHEN :status = 'running' THEN now() END)
            RETURNING id
        """), {
            "name": payload.name.strip(),
            "rules": json.dumps(payload.rules),
            "rms": json.dumps(payload.rms),
            "strategy": payload.strategy, "gap": payload.gap_seconds,
            "ws": payload.window_start, "we": payload.window_end,
            "att": payload.max_attempts, "cool": payload.cooldown_minutes,
            "status": "running" if payload.start else "draft",
            "by": user.get("email"),
        })).scalar()
        queued = await materialize(conn, cid, payload.rules)
        unowned = 0
        if payload.strategy == "assigned":
            # each lead goes to the RM it already belongs to; the rest are dropped now
            # rather than sitting in a queue nobody in this pool may claim
            unowned = await assign_owners(conn, cid, [
                (e, aliases_for(known[e.lower()]["name"], known[e.lower()]["assignment_name"]))
                for e in payload.rms
            ])

    log.info("dialer: campaign %s created by %s — %d queued, %d unowned",
             cid, user.get("email"), queued - unowned, unowned)
    return {"id": str(cid), "queued": queued - unowned, "unowned": unowned}


@router.post("/campaigns/{campaign_id}/{action}")
async def campaign_action(campaign_id: UUID, action: str, _: dict = Depends(require_admin)):
    """start / pause / stop.

    Pausing places no new calls; whatever is already ringing rings out. Stopping also
    drops the rest of the queue, so it can't be resumed.
    """
    status = {"start": "running", "pause": "paused", "stop": "done"}.get(action)
    if status is None:
        raise HTTPException(status_code=400, detail=f"unknown action {action!r}")
    engine = _engine()
    async with engine.begin() as conn:
        updated = (await conn.execute(text("""
            UPDATE dial_campaigns
               SET status = :status,
                   started_at = COALESCE(started_at, CASE WHEN :status = 'running' THEN now() END)
             WHERE id = :id RETURNING id"""), {"id": campaign_id, "status": status})).first()
        if updated is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        if action == "stop":
            await conn.execute(text(
                "UPDATE dial_queue SET status = 'skipped' "
                "WHERE campaign_id = :id AND status = 'pending'"), {"id": campaign_id})
    return {"status": status}


@router.get("/campaigns/{campaign_id}")
async def campaign_detail(campaign_id: UUID, _: dict = Depends(require_admin)):
    """Everything the live panel shows: counts, per-RM state, and the recent-calls feed."""
    engine = _engine()
    async with engine.connect() as conn:
        c = (await conn.execute(text(
            "SELECT * FROM dial_campaigns WHERE id = :id"), {"id": campaign_id})).mappings().first()
        if c is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        stats = (await conn.execute(text("""
            SELECT count(*) FILTER (WHERE status = 'pending')           AS pending,
                   count(*) FILTER (WHERE status = 'dialing')           AS live,
                   count(*) FILTER (WHERE status = 'done')              AS done,
                   count(*) FILTER (WHERE status = 'failed')            AS failed,
                   count(*) FILTER (WHERE status = 'skipped')           AS skipped,
                   count(*)                                             AS total
              FROM dial_queue WHERE campaign_id = :id"""),
            {"id": campaign_id})).mappings().first()
        per_rm = (await conn.execute(text("""
            SELECT q.rm_email,
                   count(*) FILTER (WHERE q.status = 'dialing')          AS live,
                   count(*) FILTER (WHERE q.status IN ('done','failed')) AS done
              FROM dial_queue q WHERE q.campaign_id = :id AND q.rm_email IS NOT NULL
             GROUP BY q.rm_email"""), {"id": campaign_id})).mappings().all()
        feed = (await conn.execute(text("""
            SELECT q.status, q.outcome, q.detail, q.rm_email, q.dialed_at, q.ended_at,
                   l.name AS lead_name, l.society, l.id AS lead_id,
                   cl.answered
              FROM dial_queue q
              JOIN leads l ON l.id = q.lead_id
              LEFT JOIN LATERAL (SELECT bool_or(answered) AS answered FROM call_logs
                                  WHERE event_id = q.event_id) cl ON true
             WHERE q.campaign_id = :id AND q.dialed_at IS NOT NULL
             ORDER BY q.dialed_at DESC LIMIT 25"""), {"id": campaign_id})).mappings().all()

    return {
        "campaign": {k: (str(v) if k == "id" else v) for k, v in dict(c).items()},
        "stats": dict(stats or {}),
        "per_rm": {r["rm_email"]: {"live": r["live"], "done": r["done"]} for r in per_rm},
        "feed": [{**dict(r), "lead_id": str(r["lead_id"])} for r in feed],
    }
