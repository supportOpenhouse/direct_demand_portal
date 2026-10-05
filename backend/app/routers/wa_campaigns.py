"""WhatsApp template campaigns — admin API (spec §11). Every route is admin-only."""
import logging
import uuid
import csv
import io
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import exists, func, select, text, update
from sqlalchemy.exc import IntegrityError

from ..config import get_settings
from ..core.auth import require_admin
from ..db import neon_engine
from ..models import WaAutoCampaign, WaCampaign, WaTemplate
from ..services import activity
from ..services import wa_campaigns as svc
from ..services.wa_templates import locked_changes, normalize_template

log = logging.getLogger("wa_campaigns")
router = APIRouter(tags=["wa-campaigns"], dependencies=[Depends(require_admin)])


def _engine():
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    return engine


def _template_json(t) -> dict:
    return {
        "id": str(t["id"]), "gupshup_template_id": t["gupshup_template_id"], "name": t["name"],
        "language": t["language"], "category": t["category"], "body": t["body"],
        "variable_count": t["variable_count"], "variable_labels": t["variable_labels"],
        "variable_defaults": t["variable_defaults"], "buttons": t["buttons"], "active": t["active"],
        "used": bool(t.get("used")),
    }


@router.get("/wa-campaigns/templates")
async def list_templates():
    used = exists().where(WaCampaign.template_id == WaTemplate.id)
    async with _engine().connect() as conn:
        rows = (await conn.execute(
            select(WaTemplate.__table__, used.label("used")).order_by(WaTemplate.active.desc(), WaTemplate.name)
        )).mappings().all()
    return {"items": [_template_json(r) for r in rows]}


class TemplateIn(BaseModel):
    gupshup_template_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    language: Annotated[str, StringConstraints(strip_whitespace=True)] = "en"
    category: Annotated[str | None, StringConstraints(strip_whitespace=True)] = None
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(...)
    variable_labels: list[str | None] = []
    variable_defaults: list[str | None] = []
    buttons: list[str] = []
    active: bool = True


@router.post("/wa-campaigns/templates")
async def create_template(t: TemplateIn, user: dict = Depends(require_admin)):
    # Normalize and validate
    try:
        values = normalize_template(t.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    values = values | {"created_by": user.get("email"), "updated_by": user.get("email")}
    async with _engine().begin() as conn:
        # Check for active template with same Gupshup ID only if creating an active one
        if values["active"]:
            clash = (await conn.execute(select(WaTemplate.id).where(
                WaTemplate.gupshup_template_id == values["gupshup_template_id"],
                WaTemplate.active == True,  # noqa: E712
            ))).first()
            if clash:
                raise HTTPException(status_code=409, detail="another active template already uses that Gupshup id")
        new_id = uuid.uuid4()
        try:
            await conn.execute(WaTemplate.__table__.insert().values(id=new_id, **values))
        except IntegrityError:
            raise HTTPException(status_code=409, detail="another active template already uses that Gupshup id")
        await activity.record(conn, activity.row_for(
            activity.Actor.of(user), entity_type="wa_template", entity_id=str(new_id),
            action="wa_template_created", metadata={"name": values["name"]}))
    return {"id": str(new_id)}


@router.patch("/wa-campaigns/templates/{template_id}")
async def edit_template(template_id: uuid.UUID, t: TemplateIn, user: dict = Depends(require_admin)):
    # Normalize and validate
    try:
        values = normalize_template(t.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    values = values | {"updated_by": user.get("email")}
    async with _engine().begin() as conn:
        cur = (await conn.execute(
            select(WaTemplate.__table__).where(WaTemplate.id == template_id).with_for_update()
        )).mappings().first()
        if cur is None:
            raise HTTPException(status_code=404, detail="template not found")
        used = (await conn.execute(select(WaCampaign.id).where(WaCampaign.template_id == template_id).limit(1))).first()

        # Check for locked field changes
        changes = locked_changes(dict(cur), values)
        if used and changes:
            raise HTTPException(status_code=409, detail=(
                "This template has been used by a campaign — its text and Gupshup id can't change. "
                "Deactivate it and add a new one (it may reuse the same Gupshup id)."))

        # Check if re-activating or changing ID would violate the unique index
        if values["active"] and (values["gupshup_template_id"].strip() != (cur["gupshup_template_id"] or "").strip() or
                                 not cur["active"]):
            # Either changing ID or reactivating: check for conflicts
            conflict = (await conn.execute(select(WaTemplate.id).where(
                WaTemplate.gupshup_template_id == values["gupshup_template_id"],
                WaTemplate.active == True,  # noqa: E712
                WaTemplate.id != template_id,
            ))).first()
            if conflict:
                raise HTTPException(status_code=409, detail="another active template already uses that Gupshup id")

        try:
            await conn.execute(update(WaTemplate).where(WaTemplate.id == template_id)
                               .values(**values, updated_at=func.now()))
        except IntegrityError:
            raise HTTPException(status_code=409, detail="another active template already uses that Gupshup id")

        await activity.record(conn, activity.changes_between(
            activity.Actor.of(user), "wa_template", str(template_id), dict(cur),
            {k: v for k, v in values.items() if k != "updated_by"}))
    return {"status": "ok"}


class PreviewIn(BaseModel):
    template_id: uuid.UUID
    source: Literal["upload", "paste", "wa_contacts", "repeat"]
    file_name: str | None = None
    file_b64: str | None = Field(default=None, max_length=14_000_000)  # ~10 MB file
    paste: str | None = Field(default=None, max_length=2_000_000)
    repeat_of: uuid.UUID | None = None
    repeat_mode: Literal["everyone", "non_responders"] = "everyone"
    # column indices are never negative: -1 would read from the row's END, and -9 raises IndexError
    phone_col: int = Field(default=0, ge=0)
    name_col: int | None = Field(default=None, ge=0)
    var_cols: list[Annotated[int, Field(ge=0)] | None] = []
    fixed: list[str | None] = []
    cooldown_days: int = Field(default=7, ge=0, le=365)


RETRY_SQL = text("""
    UPDATE wa_campaign_recipients SET status = 'queued', error = NULL, status_at = now()
     WHERE id = :rid AND campaign_id = :cid AND status IN ('failed', 'submitted')
    RETURNING id""")
RETRY_PEEK_SQL = text("SELECT error, status_at FROM wa_campaign_recipients WHERE id = :rid AND campaign_id = :cid")
REOPEN_SQL = text("UPDATE wa_campaigns SET status = 'sending', finished_at = NULL WHERE id = :cid AND status = 'done'")
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"  # zero-padded: the send loop compares these as TEXT against to_char(…,'HH24:MI')


class CreateIn(PreviewIn):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    send_window_start: str = Field(default="10:00", pattern=HHMM)
    send_window_end: str = Field(default="19:00", pattern=HHMM)
    rate_per_minute: int = Field(default=30, ge=1, le=600)

    @model_validator(mode="after")
    def _window_is_forward(self):
        if self.send_window_start >= self.send_window_end:
            raise ValueError("the send window must end after it starts (same day, IST)")
        return self


@router.post("/wa-campaigns/preview")
async def preview(req: PreviewIn):
    if req.source == "repeat" and not req.repeat_of:
        raise HTTPException(status_code=422, detail="pick the campaign whose list to repeat")
    async with _engine().connect() as conn:
        try:
            cands, t, headers = await svc.candidates_for(conn, req)
        except svc.NotFound as e:  # only that: IndexError / KeyError are LookupErrors, and a bug is not a 404
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        rows = await svc.classify(conn, cands, cooldown_days=req.cooldown_days,
                                  ignore_campaigns=await svc.ignore_for(conn, req))
    c = svc.counts(rows)
    return {"headers": headers, "counts": c, "rows": rows[:200], "samples": svc.samples(t, rows),
            "over_daily_limit": c["valid"] > get_settings().WA_DAILY_SEND_LIMIT,
            "daily_limit": get_settings().WA_DAILY_SEND_LIMIT}


@router.post("/wa-campaigns")
async def create_campaign(req: CreateIn, user: dict = Depends(require_admin)):
    async with _engine().begin() as conn:
        try:
            cid = await svc.create_draft(conn, req, user)
        except svc.NotFound as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    return {"id": str(cid)}


ZERO_FUNNEL = {k: 0 for k in ("recipients", "queued", "accepted", "sent", "delivered", "read", "failed",
                              "skipped", "unknown", "replied")}


@router.get("/wa-campaigns")
async def list_campaigns():
    """The newest campaigns (manual + auto runs), with counts computed from their
    recipients — never stored, so they can't drift (spec §4.2)."""
    # ponytail: newest 200, recomputed on every 15 s poll — every auto run adds a campaign, so an
    # unbounded list re-counts every send ever made. Page it (offset + "load more") past that.
    async with _engine().connect() as conn:
        rows = (await conn.execute(text("""
            SELECT c.id, c.name, c.source, c.status, c.created_at, c.launched_at, c.finished_at,
                   c.auto_campaign_id, c.repeat_of, t.name AS template_name
              FROM wa_campaigns c JOIN wa_templates t ON t.id = c.template_id
             ORDER BY c.created_at DESC
             LIMIT 200"""))).mappings().all()
        ids = [r["id"] for r in rows]
        funnel = {}
        if ids:
            for f in (await conn.execute(svc.FUNNEL_SQL, {"ids": ids})).mappings():
                funnel[f["campaign_id"]] = {k: int(f[k]) for k in ZERO_FUNNEL}
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"items": [{
        "id": str(r["id"]), "name": r["name"], "template_name": r["template_name"], "source": r["source"],
        "status": r["status"], "created_at": iso(r["created_at"]), "launched_at": iso(r["launched_at"]),
        "finished_at": iso(r["finished_at"]),
        "auto_campaign_id": str(r["auto_campaign_id"]) if r["auto_campaign_id"] else None,
        "repeat_of": str(r["repeat_of"]) if r["repeat_of"] else None,
        "counts": funnel.get(r["id"], dict(ZERO_FUNNEL)),
    } for r in rows]}


# ── Auto campaigns (spec §7) ──────────────────────────────────────────────────────
# Every /wa-campaigns/auto… route is declared HERE, above the /wa-campaigns/{cid} routes below: a GET
# /wa-campaigns/auto declared after GET /wa-campaigns/{cid} would be read as a campaign id "auto" (a 422).
class AutoIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    template_id: uuid.UUID
    seed_campaign_id: uuid.UUID
    repeat_mode: Literal["everyone", "non_responders"] = "non_responders"
    every_days: int = Field(default=1, ge=1, le=90)
    run_at: str = Field(default="11:00", pattern=HHMM)
    start_on: date                              # the first slot → next_slot
    cooldown_days: int = Field(default=7, ge=0, le=365)
    max_runs: int | None = Field(default=None, ge=1)
    send_window_start: str = Field(default="10:00", pattern=HHMM)
    send_window_end: str = Field(default="19:00", pattern=HHMM)
    rate_per_minute: int = Field(default=30, ge=1, le=600)

    @model_validator(mode="after")
    def _window_is_forward(self):
        if self.send_window_start >= self.send_window_end:
            raise ValueError("the send window must end after it starts (same day, IST)")
        return self


AUTO_SELECT_SQL = text("""
    SELECT a.*, t.name AS template_name, t.active AS template_active
      FROM wa_auto_campaigns a JOIN wa_templates t ON t.id = a.template_id
     ORDER BY a.active DESC, a.created_at DESC""")
AUTO_LAST_RUNS_SQL = text("""
    SELECT DISTINCT ON (auto_campaign_id) auto_campaign_id, id, name
      FROM wa_campaigns WHERE auto_campaign_id = ANY(:ids)
     ORDER BY auto_campaign_id, run_slot DESC, created_at DESC""")


async def _check_auto(conn, a: AutoIn) -> None:
    """The template exists and is active, the seed exists, and its list fits the template's variables."""
    t = (await conn.execute(select(WaTemplate.__table__).where(WaTemplate.id == a.template_id))).mappings().first()
    if t is None:
        raise HTTPException(status_code=404, detail="template not found")
    if not t["active"]:
        raise HTTPException(status_code=422, detail="that template is inactive")
    src = (await conn.execute(svc.SOURCE_CAMPAIGN_SQL, {"campaign_id": a.seed_campaign_id})).mappings().first()
    if src is None:
        raise HTTPException(status_code=404, detail="seed campaign not found")
    if src["variable_count"] != t["variable_count"]:
        k = src["variable_count"]
        raise HTTPException(status_code=422, detail=(
            f"The seed list was sent with a template that has {k} variable{'' if k == 1 else 's'} — pick a template with {k}"))


def _auto_values(a: AutoIn) -> dict:
    v = a.model_dump(exclude={"start_on"})
    return v | {"next_slot": a.start_on}


async def _auto_row(conn, aid: uuid.UUID):
    row = (await conn.execute(select(WaAutoCampaign.__table__).where(WaAutoCampaign.id == aid))).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="auto campaign not found")
    return row


@router.get("/wa-campaigns/auto")
async def list_autos():
    async with _engine().connect() as conn:
        rows = (await conn.execute(AUTO_SELECT_SQL)).mappings().all()
        ids = [r["id"] for r in rows]
        last, funnel = {}, {}
        if ids:
            last = {r["auto_campaign_id"]: r for r in (await conn.execute(AUTO_LAST_RUNS_SQL, {"ids": ids})).mappings()}
            if last:
                for f in (await conn.execute(svc.FUNNEL_SQL, {"ids": [r["id"] for r in last.values()]})).mappings():
                    funnel[f["campaign_id"]] = {k: int(f[k]) for k in ZERO_FUNNEL}
    return {"items": [{
        "id": str(r["id"]), "name": r["name"], "template_id": str(r["template_id"]), "template_name": r["template_name"],
        "seed_campaign_id": str(r["seed_campaign_id"]), "repeat_mode": r["repeat_mode"], "every_days": r["every_days"],
        "run_at": r["run_at"], "next_slot": r["next_slot"].isoformat(), "cooldown_days": r["cooldown_days"],
        "max_runs": r["max_runs"], "send_window_start": r["send_window_start"], "send_window_end": r["send_window_end"],
        "rate_per_minute": r["rate_per_minute"], "active": r["active"],
        # an inactive template switches the definition off silently (DUE_AUTO_SQL) — say so
        "status_note": r["status_note"] or (None if r["template_active"] else "template inactive"),
        "last_run": ({"id": str(last[r["id"]]["id"]), "name": last[r["id"]]["name"],
                      "counts": funnel.get(last[r["id"]]["id"], dict(ZERO_FUNNEL))} if r["id"] in last else None),
    } for r in rows]}


@router.post("/wa-campaigns/auto")
async def create_auto(a: AutoIn, user: dict = Depends(require_admin)):
    aid = uuid.uuid4()
    async with _engine().begin() as conn:
        await _check_auto(conn, a)
        await conn.execute(WaAutoCampaign.__table__.insert().values(
            id=aid, **_auto_values(a), active=False, created_by=user.get("email")))  # always created inactive
        await activity.record(conn, activity.row_for(
            activity.Actor.of(user), entity_type="wa_auto", entity_id=str(aid), action="wa_auto_created",
            metadata={"name": a.name, "every_days": a.every_days, "run_at": a.run_at}))
    return {"id": str(aid)}


@router.patch("/wa-campaigns/auto/{aid}")
async def edit_auto(aid: uuid.UUID, a: AutoIn, user: dict = Depends(require_admin)):
    async with _engine().begin() as conn:
        cur = await _auto_row(conn, aid)
        if a.seed_campaign_id != cur["seed_campaign_id"]:
            raise HTTPException(status_code=422, detail="the seed campaign can't change once the definition exists")
        await _check_auto(conn, a)
        values = _auto_values(a)
        await conn.execute(update(WaAutoCampaign).where(WaAutoCampaign.id == aid)
                           .values(**values, status_note=None, updated_at=func.now()))
        await activity.record(conn, activity.changes_between(
            activity.Actor.of(user), "wa_auto", str(aid), dict(cur), values))
    return {"status": "ok"}


@router.post("/wa-campaigns/auto/{aid}/dry-run")
async def dry_run_auto(aid: uuid.UUID):
    """Who the next run would message — the SAME helper a real run uses, and nothing is written."""
    async with _engine().connect() as conn:
        try:
            return await svc.auto_dry_run(conn, aid)
        except svc.NotFound as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))


@router.post("/wa-campaigns/auto/{aid}/{action}")
async def auto_action(aid: uuid.UUID, action: Literal["activate", "deactivate", "run-now"],
                      user: dict = Depends(require_admin)):
    s = get_settings()
    if action in ("activate", "run-now") and not s.gupshup_template_configured:
        raise HTTPException(status_code=503,
                            detail="Template sending isn't configured — set " + ", ".join(s.gupshup_template_missing))
    async with _engine().begin() as conn:
        cur = await _auto_row(conn, aid)
        if action in ("activate", "run-now"):
            t = (await conn.execute(select(WaTemplate.active).where(WaTemplate.id == cur["template_id"]))).first()
            if not t or not t[0]:
                raise HTTPException(status_code=409, detail="that template is inactive — pick another before switching this on")
        if action == "run-now" and not cur["active"]:
            raise HTTPException(status_code=409, detail="switch the auto campaign on first")
        if action in ("activate", "deactivate"):
            on = action == "activate"
            await conn.execute(update(WaAutoCampaign).where(WaAutoCampaign.id == aid)
                               .values(active=on, status_note=None, updated_at=func.now()))
            await activity.record(conn, activity.row_for(
                activity.Actor.of(user), entity_type="wa_auto", entity_id=str(aid),
                action=f"wa_auto_{action}d", field="active", before=cur["active"], after=on))
            return {"status": "active" if on else "inactive"}
        await activity.record(conn, activity.row_for(
            activity.Actor.of(user), entity_type="wa_auto", entity_id=str(aid), action="wa_auto_run_now"))
    # its own transactions, after the log row commits: queues today's run (the web process sends it)
    res = await svc.run_auto_campaigns(trigger="manual", only=aid)
    if not res.get("runs"):
        why = (res["skipped"][0]["reason"] if res.get("skipped") else "nothing to run")
        raise HTTPException(status_code=409, detail=f"No run was started — {why}")
    return {"status": "queued", "runs": res["runs"]}


# Registered AFTER every literal /wa-campaigns/<word> route above, so those can never be read as a campaign id.
@router.post("/wa-campaigns/{cid}/{action}")
async def campaign_action(cid: uuid.UUID, action: Literal["launch", "pause", "resume", "cancel"],
                          user: dict = Depends(require_admin)):
    s = get_settings()
    if action in ("launch", "resume") and not s.gupshup_template_configured:
        raise HTTPException(status_code=503,
                            detail="Template sending isn't configured — set " + ", ".join(s.gupshup_template_missing))
    async with _engine().begin() as conn:
        try:
            status = await svc.set_status(conn, cid, action, user)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
    return {"status": status}


@router.post("/wa-campaigns/{cid}/recipients/{rid}/retry")
async def retry_recipient(cid: uuid.UUID, rid: uuid.UUID, user: dict = Depends(require_admin)):
    async with _engine().begin() as conn:
        cur = (await conn.execute(RETRY_PEEK_SQL, {"rid": rid, "cid": cid})).mappings().first()
        if cur is not None and (why := svc.retry_refusal(cur["error"], cur["status_at"])):
            raise HTTPException(status_code=409, detail=f"Not retried: {why}")  # contract Delta 18
        row = (await conn.execute(RETRY_SQL, {"rid": rid, "cid": cid})).first()
        if row is None:
            raise HTTPException(status_code=409, detail="only a failed or unknown recipient can be retried")
        # a finished campaign goes back to sending so the loop picks the row up
        await conn.execute(REOPEN_SQL, {"cid": cid})
    return {"status": "queued"}


# ── Campaign detail. Declared AFTER every literal /wa-campaigns/<word> GET (and Task 13's /auto…
# must go above this block) so {cid} can never capture a literal path. ──────────────────────────
DETAIL_SQL = text("""
    SELECT c.id, c.name, c.source, c.status, c.status_note, c.created_at, c.launched_at, c.finished_at,
           c.auto_campaign_id, c.repeat_of, c.send_window_start, c.send_window_end, c.rate_per_minute,
           t.name AS template_name, t.body AS template_body, t.buttons AS template_buttons
      FROM wa_campaigns c JOIN wa_templates t ON t.id = c.template_id
     WHERE c.id = :cid""")
RECIPIENT_FILTERS = ("all", "accepted", "sent", "delivered", "read", "replied", "no_reply", "failed",
                     "skipped", "submitted")
_iso = lambda d: d.isoformat() if d else None  # noqa: E731


def _recipient_json(r) -> dict:
    return {
        "id": str(r["id"]), "phone10": r["phone10"], "name": r["name"], "variables": r["variables"],
        "status": r["status"], "skip_reason": r["skip_reason"], "error": r["error"], "owner": r["owner"],
        "sent_at": _iso(r["sent_at"]), "status_at": _iso(r["status_at"]), "first_reply": r["first_reply"],
        "replied_at": _iso(r["replied_at"]), "replies": int(r["replies"] or 0), "button": r["button"],
    }


async def _recipient_rows(conn, cid: uuid.UUID, status: str | None):
    if status is not None and status not in RECIPIENT_FILTERS:
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(RECIPIENT_FILTERS)}")
    return (await conn.execute(svc.RECIPIENTS_SQL, {
        "cid": cid, "status": None if status in (None, "all") else status})).mappings().all()


@router.get("/wa-campaigns/{cid}")
async def campaign_detail(cid: uuid.UUID):
    async with _engine().connect() as conn:
        c = (await conn.execute(DETAIL_SQL, {"cid": cid})).mappings().first()
        if c is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        f = (await conn.execute(svc.FUNNEL_SQL, {"ids": [cid]})).mappings().first()
        rows = await _recipient_rows(conn, cid, None)
    buttons: dict[str, int] = {}
    for r in rows:
        if r["button"]:
            buttons[r["button"]] = buttons.get(r["button"], 0) + 1
    return {
        "campaign": {
            "id": str(c["id"]), "name": c["name"], "source": c["source"], "status": c["status"],
            "status_note": c["status_note"], "created_at": _iso(c["created_at"]),
            "launched_at": _iso(c["launched_at"]), "finished_at": _iso(c["finished_at"]),
            "auto_campaign_id": str(c["auto_campaign_id"]) if c["auto_campaign_id"] else None,
            "repeat_of": str(c["repeat_of"]) if c["repeat_of"] else None,
            "send_window_start": c["send_window_start"], "send_window_end": c["send_window_end"],
            "rate_per_minute": c["rate_per_minute"], "template_name": c["template_name"],
            "template_body": c["template_body"], "template_buttons": c["template_buttons"],
        },
        "counts": {k: int(f[k]) for k in ZERO_FUNNEL} if f else dict(ZERO_FUNNEL),
        "buttons": buttons,
    }


@router.get("/wa-campaigns/{cid}/recipients")
async def campaign_recipients(cid: uuid.UUID, status: str | None = None):
    async with _engine().connect() as conn:
        rows = await _recipient_rows(conn, cid, status)
    return {"items": [_recipient_json(r) for r in rows]}


EXPORT_COLUMNS = ("name", "phone", "status", "error", "owner", "sent_at", "first_reply", "replied_at",
                  "replies", "button")


def _csv_cell(v) -> str:
    """A spreadsheet runs a cell that starts with = + - @ as a formula; names and replies are
    attacker-controlled (a customer typed them), so defuse it."""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


@router.get("/wa-campaigns/{cid}/export")
async def campaign_export(cid: uuid.UUID):
    async with _engine().connect() as conn:
        c = (await conn.execute(DETAIL_SQL, {"cid": cid})).mappings().first()
        if c is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        rows = await _recipient_rows(conn, cid, None)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(EXPORT_COLUMNS)
    for r in rows:
        j = _recipient_json(r)
        w.writerow([_csv_cell(j["name"]), j["phone10"], j["status"], _csv_cell(j["error"]), j["owner"] or "",
                    j["sent_at"] or "", _csv_cell(j["first_reply"]), j["replied_at"] or "", j["replies"],
                    _csv_cell(j["button"])])
    fname = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in c["name"]).strip() or "campaign"
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{fname}.csv"'})
