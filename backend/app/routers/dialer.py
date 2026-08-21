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
from ..services import activity
from ..services.dialer import (
    FIELDS, OPS, UNOWNED_DETAIL, aliases_for, assign_owners, compile_rules, count_matching,
    materialize, window_has_passed, windows_overlap,
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


async def _assert_no_rm_conflict(conn, rms: list[str], window_start: str, window_end: str,
                                 exclude_id=None) -> None:
    """Refuse to run a campaign that shares an RM, at overlapping hours, with one
    that's already running.

    This has to be enforced here because the scheduler can't see it: `_tick_campaign`
    counts an RM's live calls with `WHERE campaign_id = :cid`, so two running
    campaigns would each judge the same RM idle and Click2Call would ring their
    handset twice at once — the second call lands on a busy line and the queue item
    burns an attempt for nothing.
    """
    rows = (await conn.execute(text(
        "SELECT id, name, rms, window_start, window_end FROM dial_campaigns "
        "WHERE status = 'running'"))).mappings().all()
    wanted = {e.lower() for e in rms}
    for r in rows:
        if exclude_id is not None and r["id"] == exclude_id:
            continue
        shared = sorted(wanted & {str(e).lower() for e in (r["rms"] or [])})
        if not shared:
            continue
        if windows_overlap(window_start, window_end, r["window_start"], r["window_end"]):
            raise HTTPException(status_code=409, detail=(
                f"{shared[0]} is already dialling on '{r['name']}' "
                f"({r['window_start']}–{r['window_end']}). Pause that campaign, drop that RM, "
                f"or pick a calling window that doesn't overlap."
            ))


# Who a campaign may dial. Calling roles only: the pool is who does the calling, and
# Click2Call rings their own handset. Admins run campaigns; they aren't dialled by
# them. `role` comes back so the picker can tag a test_rm as TEST — an admin building
# a campaign needs to see at a glance whether they're aiming at a real handset.
_CALLABLE_RMS = text("""
    SELECT email, name, assignment_name, phone, role
      FROM users
     WHERE active AND role IN ('rm', 'test_rm')
     ORDER BY name NULLS LAST, email
""")


def _assert_window_not_over(window_start: str, window_end: str) -> None:
    """Refuse to start a campaign whose calling window already closed today.

    Nothing downstream reports this: the campaign reaches 'running', _in_window is
    false all evening, and it dials nobody until tomorrow morning while looking
    perfectly healthy on the dashboard.
    """
    if window_has_passed(window_start, window_end):
        raise HTTPException(status_code=422, detail=(
            f"that calling window ({window_start}–{window_end} IST) has already ended "
            f"today — nothing would be dialled until tomorrow. Widen the window or "
            f"save it as a draft and start it in the morning."
        ))


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
    cooldown_minutes: int = Field(default=180, ge=0, le=10080)
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
        rms = (await conn.execute(_CALLABLE_RMS)).mappings().all()
    return {
        "fields": [
            {"key": k, "label": v["label"], "kind": v["kind"],
             "ops": sorted(OPS[v["kind"]]), "options": options.get(k, [])}
            for k, v in FIELDS.items()
        ],
        "rms": [
            {"email": r["email"], "name": r["name"] or r["assignment_name"] or r["email"],
             "has_phone": bool(r["phone"]), "role": r["role"]}
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
            users = (await conn.execute(_CALLABLE_RMS)).mappings().all()
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
                   count(q.id)                                                AS total,
                   -- what the campaign was actually pointed at. Under 'assigned' the
                   -- queue holds every rule match, then the ones nobody in the pool
                   -- owns are skipped — those were never targeted, so counting them
                   -- reported 1727 for a campaign aimed at one RM's 4 leads. Rows
                   -- skipped by Stop still count: they were targeted, just not reached.
                   count(q.id) FILTER (
                       WHERE q.status <> 'skipped' OR q.detail IS DISTINCT FROM :unowned
                   )                                                          AS targeted,
                   -- with retries on, calls > leads: one queue row can be dialled
                   -- max_attempts times, so `attempts` is the only honest call count
                   count(q.id) FILTER (WHERE q.attempts > 0)                  AS unique_leads,
                   COALESCE(sum(q.attempts), 0)                               AS total_calls,
                   count(q.id) FILTER (WHERE q.answered)                      AS connected
              FROM dial_campaigns c LEFT JOIN dial_queue q ON q.campaign_id = c.id
             GROUP BY c.id ORDER BY c.created_at DESC LIMIT 50
        """), {"unowned": UNOWNED_DETAIL})).mappings().all()
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
        # The calling-role filter is enforced here, not just hidden in the picker —
        # otherwise a hand-rolled POST could still queue calls to an admin's handset.
        users = (await conn.execute(_CALLABLE_RMS)).mappings().all()
        known = {u["email"].lower(): u for u in users}
        unknown = [e for e in payload.rms if e.lower() not in known]
        if unknown:
            raise HTTPException(status_code=400, detail=f"not an active RM: {unknown[0]}")
        if payload.start:  # a draft dials nothing, so it can't conflict yet
            _assert_window_not_over(payload.window_start, payload.window_end)
            await _assert_no_rm_conflict(conn, payload.rms, payload.window_start, payload.window_end)

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
async def campaign_action(campaign_id: UUID, action: str,
                          user: dict = Depends(require_admin)):
    """start / pause / stop.

    Pausing places no new calls; whatever is already ringing rings out. Stopping also
    drops the rest of the queue, so it can't be resumed.
    """
    status = {"start": "running", "pause": "paused", "stop": "done"}.get(action)
    if status is None:
        raise HTTPException(status_code=400, detail=f"unknown action {action!r}")
    engine = _engine()
    async with engine.begin() as conn:
        # Resuming is starting: the same conflict has to be caught here, or you could
        # create a draft (or pause one) and walk it into an overlap the create path
        # would have refused.
        if status == "running":
            me = (await conn.execute(text(
                "SELECT rms, window_start, window_end FROM dial_campaigns WHERE id = :id"),
                {"id": campaign_id})).mappings().first()
            if me is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            # Same reasoning: a draft saved this morning must not be startable at 20:00
            # into a window that closed at 19:00.
            _assert_window_not_over(me["window_start"], me["window_end"])
            await _assert_no_rm_conflict(conn, [str(e) for e in (me["rms"] or [])],
                                         me["window_start"], me["window_end"],
                                         exclude_id=campaign_id)
        updated = (await conn.execute(text("""
            UPDATE dial_campaigns
               SET status = :status,
                   started_at = COALESCE(started_at, CASE WHEN :status = 'running' THEN now() END)
             WHERE id = :id RETURNING id"""), {"id": campaign_id, "status": status})).first()
        if updated is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        # Starting a campaign sets other people's phones ringing. Who did that, and
        # who stopped it, is exactly the kind of thing nobody remembers an hour later.
        await activity.record(conn, activity.row_for(
            activity.Actor.of(user), entity_type="campaign", entity_id=campaign_id,
            action=f"campaign_{action}", field="status", after=status))
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
                   count(*)                                             AS total,
                   -- leads this campaign was pointed at: every rule match lands in the
                   -- queue, but under 'assigned' the ones nobody in the pool owns are
                   -- skipped and were never really targeted. Stop-skipped rows do count.
                   count(*) FILTER (
                       WHERE status <> 'skipped' OR detail IS DISTINCT FROM :unowned
                   )                                                    AS targeted,
                   -- with max_attempts > 1 a lead can be rung several times, so leads
                   -- and calls diverge and both matter
                   count(*) FILTER (WHERE attempts > 0)                 AS unique_leads,
                   COALESCE(sum(attempts), 0)                           AS total_calls,
                   count(*) FILTER (WHERE answered)                     AS connected
              FROM dial_queue WHERE campaign_id = :id"""),
            {"id": campaign_id, "unowned": UNOWNED_DETAIL})).mappings().first()
        per_rm = (await conn.execute(text("""
            SELECT q.rm_email,
                   count(*) FILTER (WHERE q.status = 'dialing')          AS live,
                   count(*) FILTER (WHERE q.status IN ('done','failed')) AS done
              FROM dial_queue q WHERE q.campaign_id = :id AND q.rm_email IS NOT NULL
             GROUP BY q.rm_email"""), {"id": campaign_id})).mappings().all()
        feed = (await conn.execute(text("""
            SELECT q.status, q.outcome, q.detail, q.rm_email, q.dialed_at, q.ended_at,
                   q.event_id, q.attempts, q.answered,
                   l.name AS lead_name, l.society, l.id AS lead_id
              FROM dial_queue q
              JOIN leads l ON l.id = q.lead_id
             WHERE q.campaign_id = :id AND q.dialed_at IS NOT NULL
             ORDER BY q.dialed_at DESC LIMIT 25"""), {"id": campaign_id})).mappings().all()

    return {
        "campaign": {k: (str(v) if k == "id" else v) for k, v in dict(c).items()},
        "stats": dict(stats or {}),
        "per_rm": {r["rm_email"]: {"live": r["live"], "done": r["done"]} for r in per_rm},
        "feed": [{**dict(r), "lead_id": str(r["lead_id"])} for r in feed],
    }
