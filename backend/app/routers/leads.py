from datetime import date, datetime, timedelta, timezone
from math import ceil
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..core.auth import assignment_aliases, current_user
from ..db import neon_engine
from ..models import LeadConfirmedData, LeadNote, Visit
from ..services.leads_sync import read_leads_state, run_leads_sync
from ..services.matching import match_lead, match_preview
from ..services.societies import (
    localities_in_micromarket,
    search_localities,
    search_micromarkets,
    search_societies,
    societies_in_city,
    societies_in_locality,
)

router = APIRouter(tags=["leads"], dependencies=[Depends(current_user)])

# The eight stages a lead can hold. `stage` is authoritative: every page is a plain
# equality on it, so a lead lives on exactly one page and can never fall between them.
# (The previous model derived pages from confirmed/follow_up_at/qualified_at/crm_visits
# and needed a catch-all clause to stop worked leads vanishing entirely.)
STAGES = ("new", "call_not_received", "follow_up", "qualified",
          "visit_scheduled", "won", "rejected", "rnr")

# stages a lead never moves back out of on its own
_TERMINAL = "('won','rejected','rnr')"

# segment → SQL predicate. One page per stage, except Rejected which also holds RNR
# (10 missed calls, never reached) — those keep stage='rnr' and show an RNR badge.
SEGMENTS = {
    "new": "stage = 'new'",
    "call_not_received": "stage = 'call_not_received'",
    "followup": "stage = 'follow_up'",
    "qualified": "stage = 'qualified'",
    "pipeline": "stage = 'visit_scheduled'",
    "converted": "stage = 'won'",
    "rejected": "stage IN ('rejected','rnr')",
}


def _parse_followup(raw: str | None) -> datetime:
    """Parse a required ISO-8601 UTC follow-up time (frontend sends `…Z`)."""
    if not raw:
        raise HTTPException(status_code=422, detail={"fields": ["follow_up_at"], "message": "follow-up is required"})
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail={"fields": ["follow_up_at"]})


def _lead_row(r) -> dict:
    # source remarks (seeded, " | "-joined) + manual lead_notes form the thread; the
    # list query supplies the newest manual note + its count (None on other queries).
    remarks = [p.strip() for p in (r["source_remarks"] or "").split(" | ") if p.strip()]
    return {
        "id": str(r["id"]),
        "source_category": r["source_category"],
        "source": r["source"],
        "name": r["name"],
        "phone": r["phone"],
        "email": r["email"],
        "assigned_to": r["assigned_to"],
        "city": r["city"],
        "society": r["society"],
        "configuration": r["configuration"],
        "budget_band": r["budget_band"],
        "plan_to_buy": r["plan_to_buy"],
        "preferred_visit_day": r["preferred_visit_day"],
        "source_remarks": r["source_remarks"],
        "source_meta": r["source_meta"],
        "received_at": r["received_at"].isoformat() if r["received_at"] else None,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "stage": r["stage"],
        "tat_deadline": r["tat_deadline"].isoformat() if r["tat_deadline"] else None,
        "reject_reason": r["reject_reason"],
        "reject_notes": r["reject_notes"],
        "rejected_at": r["rejected_at"].isoformat() if r["rejected_at"] else None,
        "confirmed": r["confirmed"],
        "qualified_at": r["qualified_at"].isoformat() if r["qualified_at"] else None,
        "follow_up_since": r["follow_up_since"].isoformat() if r["follow_up_since"] else None,
        "follow_up_at": r["follow_up_at"].isoformat() if r["follow_up_at"] else None,
        "miss_count": r["miss_count"] or 0,
        # lets the worklist refuse a spammed "No" before opening the reason form —
        # the server still enforces the cooldown, this only saves wasted typing
        "last_no_timestamp": (r["last_no_timestamp"].isoformat()
                              if r.get("last_no_timestamp") else None),
        "ever_connected": r["ever_connected"],
        "is_hot": bool(r["is_hot"]),
        # latest booked visit (Pipeline status chip) — only present on the list query
        "visit_status": r.get("visit_status"),
        "visit_date": r.get("visit_sel_date"),
        "visit_count": int(r.get("visit_count") or 0),
        "latest_note": r.get("latest_note_body") or (remarks[-1] if remarks else None),
        "latest_note_at": r["latest_note_at"].isoformat() if r.get("latest_note_at") else None,
        "note_count": int(r.get("note_count") or 0) + len(remarks),
        "is_test": r["is_test"],
    }


def _role_scope(user: dict) -> tuple[str, dict]:
    """Row visibility by role, as a standalone boolean clause: admins see everything,
    CM sees all assigned leads (no unassigned), RM sees only their own. Shared by the
    list and the counts endpoints so both scope identically."""
    role = user.get("role")
    if role == "cm":
        return "assigned_to IS NOT NULL", {}
    if role == "rm":
        aliases = assignment_aliases(user)
        return ("lower(assigned_to) = ANY(:aliases)", {"aliases": aliases}) if aliases else ("false", {})
    return "true", {}


@router.get("/leads")
async def list_leads(segment: str = Query("new"), user: dict = Depends(current_user)):
    engine = neon_engine()
    if engine is None:
        return {"status": "not_configured", "detail": "Set DATABASE_URL", "items": [], "sync": None}
    predicate = SEGMENTS.get(segment)
    if predicate is None:
        raise HTTPException(status_code=400, detail=f"unknown segment '{segment}'")
    scope, params = _role_scope(user)
    predicate = f"({predicate}) AND ({scope})"
    # Follow-up is a worklist — soonest/overdue callbacks first; others newest-first.
    order = "follow_up_at ASC NULLS LAST" if segment == "followup" else "created_at DESC"
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text(
                    "SELECT leads.*, "
                    "(SELECT body FROM lead_notes WHERE lead_id = leads.id ORDER BY created_at DESC LIMIT 1) AS latest_note_body, "
                    "(SELECT created_at FROM lead_notes WHERE lead_id = leads.id ORDER BY created_at DESC LIMIT 1) AS latest_note_at, "
                    "(SELECT count(*) FROM lead_notes WHERE lead_id = leads.id) AS note_count, "
                    "(SELECT status FROM crm_visits WHERE lead_id = leads.id ORDER BY created_at DESC LIMIT 1) AS visit_status, "
                    "(SELECT selected_date FROM crm_visits WHERE lead_id = leads.id ORDER BY created_at DESC LIMIT 1) AS visit_sel_date, "
                    "(SELECT count(*) FROM crm_visits WHERE lead_id = leads.id) AS visit_count "
                    f"FROM leads WHERE {predicate} ORDER BY is_test DESC, {order}"
                ),
                params,
            )
            items = [_lead_row(m) for m in res.mappings()]
            # on the same connection — a second checkout here costs another round trip
            sync = await read_leads_state(conn)
    except Exception as e:  # table missing / conn error
        return {"status": "error", "detail": str(e), "items": [], "sync": None}
    return {"status": "ok", "detail": None, "items": items, "sync": sync}


@router.get("/leads/counts")
async def lead_counts(user: dict = Depends(current_user)):
    """Per-segment counts + role-scoped total, in one query. Each segment count reuses
    the exact SEGMENTS predicate (via count(*) FILTER) so it can never drift from the
    list pages. `total` is every lead the caller may see — the % denominator."""
    engine = neon_engine()
    if engine is None:
        return {"status": "not_configured", "counts": {}, "total": 0}
    scope, params = _role_scope(user)
    cols = ", ".join(f'count(*) FILTER (WHERE {pred}) AS "{seg}"' for seg, pred in SEGMENTS.items())
    try:
        async with engine.connect() as conn:
            row = (await conn.execute(
                text(f"SELECT {cols}, count(*) AS total, "
                     f"count(*) FILTER (WHERE NOT is_test) AS total_nontest FROM leads WHERE {scope}"), params
            )).mappings().one()
    except Exception as e:
        return {"status": "error", "detail": str(e), "counts": {}, "total": 0, "total_nontest": 0}
    counts = {seg: int(row[seg]) for seg in SEGMENTS}
    return {"status": "ok", "counts": counts, "total": int(row["total"]),
            "total_nontest": int(row["total_nontest"])}


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: UUID):
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT leads.*, "
            "(SELECT count(*) FROM crm_visits WHERE lead_id = leads.id) AS visit_count "
            "FROM leads WHERE id = :id"), {"id": lead_id})
        row = res.mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="lead not found")
        lead = _lead_row(row)
        cres = await conn.execute(
            text("SELECT * FROM lead_confirmed_data WHERE lead_id = :id"), {"id": lead_id}
        )
        c = cres.mappings().first()
    def _num(v):
        return float(v) if v is not None else None
    lead["confirmed_data"] = (
        {
            "purpose": c["purpose"],
            "budget_min_lacs": _num(c["budget_min_lacs"]),
            "budget_max_lacs": _num(c["budget_max_lacs"]),
            "configuration": c["configuration"],
            "size_min_sqft": _num(c["size_min_sqft"]),
            "size_max_sqft": _num(c["size_max_sqft"]),
            "preferred_micromarkets": c["preferred_micromarkets"],
            "shortlisted_societies": c["shortlisted_societies"],
            "preferred_localities": c["preferred_localities"],
            "office_willing": c["office_willing"],
            "office_preferred_date": c["office_preferred_date"].isoformat() if c["office_preferred_date"] else None,
            "remark": c["remark"],
            "confirmed_at": c["confirmed_at"].isoformat() if c["confirmed_at"] else None,
        }
        if c
        else None
    )
    return lead


@router.get("/leads/{lead_id}/matches")
async def lead_matches(lead_id: UUID):
    """Top-5 live inventory + top-5 supply units matched to this lead."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT * FROM leads WHERE id = :id"), {"id": lead_id})
        row = res.mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="lead not found")
        cres = await conn.execute(
            text("SELECT * FROM lead_confirmed_data WHERE lead_id = :id"), {"id": lead_id}
        )
        c = cres.mappings().first()
    confirmed = dict(c) if c else None
    return await match_lead(dict(row), confirmed)


class MatchPreview(BaseModel):
    city: str | None = None
    societies: list[str] = []
    localities: list[str] = []
    micromarkets: list[str] = []
    configuration: str | None = None
    size_min_sqft: float | None = None
    size_max_sqft: float | None = None
    budget_min_lacs: float | None = None
    budget_max_lacs: float | None = None
    budget_band: str | None = None


@router.post("/leads/match-preview")
async def leads_match_preview(payload: MatchPreview):
    """Live matching for in-progress form fields — units are cached, so this is fast."""
    return await match_preview(payload.model_dump())


class ConfirmPayload(BaseModel):
    purpose: str
    budget_min_lacs: float
    budget_max_lacs: float
    configuration: str
    size_min_sqft: float | None = None
    size_max_sqft: float | None = None
    preferred_micromarkets: list[str] = []
    shortlisted_societies: list[str] = []
    preferred_localities: list[str] = []
    office_willing: str
    office_preferred_date: str | None = None
    remark: str | None = None
    # follow-up is mandatory to qualify or to save-with-callback; omitted (null) means
    # "save the details only" — used for Pipeline leads, which are past qualification and
    # shouldn't be forced to set a callback or re-qualify.
    follow_up_at: str | None = None
    qualify: bool = True          # True → qualify the lead; False → save details (+ follow-up if given)


@router.post("/leads/{lead_id}/confirm")
async def confirm_lead(lead_id: UUID, payload: ConfirmPayload):
    """Save the confirmed-on-call form + a mandatory follow-up. `qualify=true` moves the
    lead to stage 'qualified'; `qualify=false` saves the details and moves it to
    'follow_up' instead."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    # mandatory: purpose, budget range, config, office-willing
    missing = [
        f for f, v in [("purpose", payload.purpose), ("budget_min_lacs", payload.budget_min_lacs),
                       ("budget_max_lacs", payload.budget_max_lacs),
                       ("configuration", payload.configuration), ("office_willing", payload.office_willing)]
        if v in (None, "", 0)
    ]
    if missing:
        raise HTTPException(status_code=422, detail={"fields": missing})
    if payload.budget_min_lacs > payload.budget_max_lacs:
        raise HTTPException(status_code=422, detail={"fields": ["budget_max_lacs"], "message": "max must be ≥ min"})
    # a follow-up is required to qualify or to save-with-callback, but not for a pure
    # save (Pipeline leads pass follow_up_at = null)
    follow_up = _parse_followup(payload.follow_up_at) if payload.follow_up_at else None
    if payload.qualify and follow_up is None:
        raise HTTPException(status_code=422, detail={"fields": ["follow_up_at"], "message": "follow-up is required to qualify"})
    office_date: date | None = None
    if payload.office_preferred_date:
        try:
            office_date = date.fromisoformat(payload.office_preferred_date)
        except ValueError:
            raise HTTPException(status_code=422, detail={"fields": ["office_preferred_date"]})
    from ..services.normalize import normalize_config
    values = dict(
        lead_id=lead_id, purpose=payload.purpose, budget_value_lacs=None, size_sqft=None,
        budget_min_lacs=payload.budget_min_lacs, budget_max_lacs=payload.budget_max_lacs,
        configuration=normalize_config(payload.configuration),
        size_min_sqft=payload.size_min_sqft, size_max_sqft=payload.size_max_sqft,
        preferred_micromarkets=payload.preferred_micromarkets,
        shortlisted_societies=payload.shortlisted_societies, preferred_localities=payload.preferred_localities,
        office_willing=payload.office_willing, office_preferred_date=office_date, remark=payload.remark,
    )
    async with engine.begin() as conn:
        exists = await conn.execute(text("SELECT stage FROM leads WHERE id = :id"), {"id": lead_id})
        if exists.first() is None:
            raise HTTPException(status_code=404, detail="lead not found")
        stmt = pg_insert(LeadConfirmedData).values(**values).on_conflict_do_update(
            index_elements=[LeadConfirmedData.lead_id],
            set_={k: v for k, v in values.items() if k != "lead_id"},
        )
        await conn.execute(stmt)
        # reaching this form means the call connected → never RNR.
        if payload.qualify:
            # → Qualified. follow_up_at is kept so the Qualified page can badge a due
            # callback; the lead no longer also appears in the Follow-up list.
            await conn.execute(
                text(
                    "UPDATE leads SET confirmed = true, ever_connected = true, miss_count = 0, "
                    f"stage = CASE WHEN stage IN {_TERMINAL} THEN stage ELSE 'qualified' END, "
                    "tat_deadline = NULL, follow_up_at = :t, "
                    "follow_up_since = COALESCE(follow_up_since, now()), "
                    "qualified_at = COALESCE(qualified_at, now()) WHERE id = :id"
                ),
                {"id": lead_id, "t": follow_up},
            )
        elif follow_up is not None:
            # details saved but not qualified → Follow-up
            await conn.execute(
                text("UPDATE leads SET ever_connected = true, miss_count = 0, follow_up_at = :t, "
                     "follow_up_since = COALESCE(follow_up_since, now()), "
                     f"stage = CASE WHEN stage IN {_TERMINAL} OR stage IN "
                     "('qualified','visit_scheduled') THEN stage ELSE 'follow_up' END "
                     "WHERE id = :id"),
                {"id": lead_id, "t": follow_up},
            )
        else:
            # details only, no callback. The call still connected, so a lead sitting in
            # New / Call Not Received has to move — leaving it would contradict
            # ever_connected. Forward-only: qualified and beyond are untouched.
            await conn.execute(
                text("UPDATE leads SET ever_connected = true, miss_count = 0, "
                     "stage = CASE WHEN stage IN ('new','call_not_received') "
                     "THEN 'follow_up' ELSE stage END WHERE id = :id"),
                {"id": lead_id},
            )
    return {"status": "ok"}


# --- call worklist (New Leads / Follow-up) -----------------------------------

IST = timezone(timedelta(hours=5, minutes=30))
WORK_START_HOUR, WORK_END_HOUR = 10, 19  # calling hours, IST

# "No" on the worklist → why, and what it costs the lead. Value = auto follow-up
# delay in hours; None = the number is unusable, so the lead is rejected outright.
# Spam guard: a second "No" on the same lead inside this window is rejected outright.
# Without it, repeated clicks inflate miss_count and can push a lead to RNR in seconds.
NO_COOLDOWN_HOURS = 2

MISS_REASONS: dict[str, int | None] = {
    "Did Not Pick / Not Reachable": 3,
    "Switched Off": 6,
    "Invalid Number": None,
}


def _within_calling_hours(dt: datetime) -> datetime:
    """Clamp an AUTO-computed follow-up into the 10:00–19:00 IST calling window:
    before 10:00 → same day 10:00, at/after 19:00 → next day 10:00. Manually set
    follow-ups deliberately bypass this — the RM may book any time the buyer asks for."""
    local = dt.astimezone(IST)
    if local.hour < WORK_START_HOUR:
        local = local.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    elif local.hour >= WORK_END_HOUR:
        local = (local + timedelta(days=1)).replace(
            hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


class CallResult(BaseModel):
    connected: bool
    reason: str | None = None
    notes: str | None = None


@router.post("/leads/{lead_id}/call-result")
async def call_result(lead_id: UUID, payload: CallResult, user: dict = Depends(current_user)):
    """Log a call attempt from the New Leads / Follow-up worklist.
    connected=True  → opens the lead (caller navigates); resets the miss streak.
    connected=False → reason + notes are both mandatory. Did Not Pick → +3h,
    Switched Off → +6h (both clamped to calling hours); Invalid Number → Rejected.
    10 consecutive misses on a never-connected lead still escalate to RNR."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")

    note = (payload.notes or "").strip()
    if not payload.connected:
        if payload.reason not in MISS_REASONS:
            raise HTTPException(status_code=422, detail={"fields": ["reason"], "message": "pick a reason"})
        if not note:
            raise HTTPException(status_code=422, detail={"fields": ["notes"], "message": "notes are required"})
    author = user.get("name") or user.get("email") or "You"

    async with engine.begin() as conn:
        if payload.connected:
            # We reached them, so New / Call Not Received no longer describes the lead —
            # move it to Follow-up. The caller usually opens the lead and confirms next,
            # which overwrites this; the move matters when they don't. Forward-only.
            res = await conn.execute(text(
                "UPDATE leads SET ever_connected = true, miss_count = 0, "
                "stage = CASE WHEN stage IN ('new','call_not_received') "
                "THEN 'follow_up' ELSE stage END WHERE id = :id"), {"id": lead_id})
            if res.rowcount == 0:
                raise HTTPException(status_code=404, detail="lead not found")
            return {"status": "ok", "connected": True, "moved_to_rnr": False, "rejected": False}

        # One round trip: append the note and apply the outcome together. This runs on
        # every "No" from the worklist, and each extra statement is a full Neon
        # round trip — the branch (RNR vs reschedule) is decided in SQL off the
        # pre-update row so we never need to read it first.
        reject = MISS_REASONS[payload.reason] is None
        due = None if reject else _within_calling_hours(
            datetime.now(timezone.utc) + timedelta(hours=MISS_REASONS[payload.reason]))
        # `cur` snapshots the row BEFORE the update (a CTE sees the statement's
        # snapshot), which is what lets one statement both test the spam window and
        # apply the outcome. When blocked, every SET below writes the column back to
        # its own value and the note is never inserted — so a spammed "No" leaves no
        # trace at all, and in particular can't inflate miss_count toward RNR.
        res = await conn.execute(text(f"""
            WITH cur AS (
                SELECT id, last_no_timestamp AS prev,
                       (last_no_timestamp IS NOT NULL
                        AND last_no_timestamp > now() - interval '{NO_COOLDOWN_HOURS} hours') AS blocked
                FROM leads WHERE id = :id
            ),
            n AS (
                -- FROM cur doubles as the existence guard: a stale lead id yields no
                -- row, so the note is skipped and the UPDATE returns nothing (→ 404)
                -- rather than blowing up on the note's foreign key
                INSERT INTO lead_notes (id, lead_id, body, author, source, created_at)
                SELECT :nid, :id, :note, :author, 'call', now() FROM cur WHERE NOT cur.blocked
            )
            UPDATE leads SET
                miss_count = CASE WHEN cur.blocked THEN leads.miss_count
                             WHEN CAST(:reject AS boolean) THEN leads.miss_count
                             ELSE leads.miss_count + 1 END,
                -- never reached → Call Not Received; already reached → Follow-up.
                -- Qualified and beyond keep their stage: a missed callback on a
                -- qualified lead must not drag it back down the funnel.
                stage = CASE WHEN cur.blocked THEN leads.stage
                             WHEN CAST(:reject AS boolean) THEN 'rejected'
                             WHEN NOT leads.ever_connected AND leads.miss_count + 1 >= 10 THEN 'rnr'
                             WHEN leads.stage IN ('qualified','visit_scheduled','won') THEN leads.stage
                             WHEN NOT leads.ever_connected THEN 'call_not_received'
                             ELSE 'follow_up' END,
                follow_up_at = CASE WHEN cur.blocked THEN leads.follow_up_at
                             WHEN CAST(:reject AS boolean)
                                  OR (NOT leads.ever_connected AND leads.miss_count + 1 >= 10) THEN NULL
                             ELSE CAST(:due AS timestamptz) END,
                follow_up_since = CASE WHEN cur.blocked THEN leads.follow_up_since
                             WHEN CAST(:reject AS boolean)
                                  OR (NOT leads.ever_connected AND leads.miss_count + 1 >= 10) THEN NULL
                             ELSE COALESCE(leads.follow_up_since, now()) END,
                reject_reason = CASE WHEN NOT cur.blocked AND CAST(:reject AS boolean)
                             THEN CAST(:reason AS text) ELSE leads.reject_reason END,
                reject_notes  = CASE WHEN NOT cur.blocked AND CAST(:reject AS boolean)
                             THEN CAST(:note AS text) ELSE leads.reject_notes END,
                rejected_at   = CASE WHEN NOT cur.blocked AND CAST(:reject AS boolean)
                             THEN now() ELSE leads.rejected_at END,
                last_no_timestamp = CASE WHEN cur.blocked THEN leads.last_no_timestamp
                             ELSE now() END
            FROM cur
            WHERE leads.id = cur.id
            RETURNING leads.miss_count, leads.stage, cur.blocked,
                      cur.prev + interval '{NO_COOLDOWN_HOURS} hours' AS retry_at
        """), {"nid": uuid4(), "id": lead_id, "note": note, "author": author,
               "reject": reject, "reason": payload.reason, "due": due})
        out = res.mappings().first()
        if out is None:
            raise HTTPException(status_code=404, detail="lead not found")

    if out["blocked"]:
        remaining = (out["retry_at"] - datetime.now(timezone.utc)).total_seconds() / 60
        return {"status": "blocked", "connected": False, "blocked": True,
                "retry_in_minutes": max(1, ceil(remaining)),
                "moved_to_rnr": False, "rejected": False, "miss_count": out["miss_count"]}

    to_rnr = out["stage"] == "rnr"
    return {"status": "ok", "connected": False, "blocked": False, "moved_to_rnr": to_rnr,
            "rejected": reject, "miss_count": out["miss_count"],
            "follow_up_at": None if (reject or to_rnr) else due.isoformat()}


class FollowupPayload(BaseModel):
    follow_up_at: str


@router.post("/leads/{lead_id}/followup")
async def set_followup(lead_id: UUID, payload: FollowupPayload):
    """Set a manual follow-up (reachable only after a connected call) → moves to Follow-up."""
    follow_up = _parse_followup(payload.follow_up_at)
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        res = await conn.execute(
            text("UPDATE leads SET follow_up_at = :t, ever_connected = true, miss_count = 0, "
                 "follow_up_since = COALESCE(follow_up_since, now()), "
                 # a qualified lead keeps its stage — the callback shows as a due badge
                 # on the Qualified page rather than demoting it
                 f"stage = CASE WHEN stage IN {_TERMINAL} OR stage IN "
                 "('qualified','visit_scheduled') THEN stage ELSE 'follow_up' END "
                 "WHERE id = :id"),
            {"t": follow_up, "id": lead_id})
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
    return {"status": "ok"}


@router.get("/leads/{lead_id}/crm-visits")
async def lead_crm_visits(lead_id: UUID):
    """Every visit booked on the Openhouse app for this lead — each has its own visit id
    and is a separate visit (a buyer often tours several societies)."""
    engine = neon_engine()
    if engine is None:
        return {"items": []}
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT visit_id, home_id, society, city, selected_date, selected_time, status, "
            "visit_date, buyer_feedback, sales_feedback, booked_by FROM crm_visits "
            "WHERE lead_id = :id ORDER BY selected_date DESC NULLS LAST, visit_id DESC"
        ), {"id": lead_id})).mappings().all()
    return {"items": [dict(r) for r in rows]}


class HotPayload(BaseModel):
    hot: bool


@router.post("/leads/{lead_id}/hot")
async def mark_hot(lead_id: UUID, payload: HotPayload):
    """Star / un-star a lead as hot (used by the Pipeline tab's filter)."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        res = await conn.execute(
            text("UPDATE leads SET is_hot = :h WHERE id = :id"), {"h": payload.hot, "id": lead_id})
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
    return {"status": "ok", "is_hot": payload.hot}


# every value reject_reason can hold. "Invalid Number" is only ever set by the
# worklist's No → Invalid Number path, not offered in the manual reject dropdown.
REJECT_REASONS = {"Broker", "Budget", "Location", "Requirement Mismatch", "No Requirement",
                  "Invalid Number"}


class RejectPayload(BaseModel):
    reason: str
    notes: str


@router.post("/leads/{lead_id}/reject")
async def reject_lead(lead_id: UUID, payload: RejectPayload):
    if payload.reason not in REJECT_REASONS:
        raise HTTPException(status_code=422, detail={"fields": ["reason"]})
    if not payload.notes.strip():
        raise HTTPException(status_code=422, detail={"fields": ["notes"], "message": "notes are required"})
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        res = await conn.execute(text(
            "UPDATE leads SET stage='rejected', reject_reason=:r, reject_notes=:n, rejected_at=now() WHERE id=:id"),
            {"r": payload.reason, "n": payload.notes.strip(), "id": lead_id})
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
    return {"status": "ok"}


@router.post("/leads/sync")
async def sync_leads():
    result = await run_leads_sync(trigger="manual")
    if result["status"] == "not_configured":
        raise HTTPException(status_code=503, detail=result.get("detail"))
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result.get("detail"))
    return result


# --- editable source-captured card ------------------------------------------

class SourceDataPatch(BaseModel):
    city: str | None = None
    society: str | None = None
    configuration: str | None = None
    budget_band: str | None = None
    plan_to_buy: str | None = None
    source_remarks: str | None = None


@router.patch("/leads/{lead_id}/source-data")
async def patch_source_data(lead_id: UUID, payload: SourceDataPatch):
    sets, params = [], {"id": lead_id}
    for field in ("city", "society", "configuration", "budget_band", "plan_to_buy", "source_remarks"):
        val = getattr(payload, field)
        if val is not None:
            sets.append(f"{field} = :{field}")
            params[field] = val or None
    if not sets:
        return {"status": "noop"}
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        res = await conn.execute(text(f"UPDATE leads SET {', '.join(sets)} WHERE id = :id"), params)
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
    return {"status": "ok"}


# --- remarks thread ----------------------------------------------------------

@router.get("/leads/{lead_id}/notes")
async def list_notes(lead_id: UUID):
    """Seed messages from the sheet's Remarks / Remarks 2 + appended notes, oldest first."""
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.connect() as conn:
        lead = (await conn.execute(
            text("SELECT source_remarks, received_at, source FROM leads WHERE id = :id"), {"id": lead_id}
        )).mappings().first()
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        notes = (await conn.execute(
            text("SELECT id, body, author, source, created_at FROM lead_notes WHERE lead_id = :id ORDER BY created_at"),
            {"id": lead_id},
        )).mappings().all()

    thread = []
    if lead["source_remarks"]:
        for part in [p.strip() for p in lead["source_remarks"].split(" | ") if p.strip()]:
            thread.append({
                "id": None, "body": part, "author": f"From {lead['source']}", "source": "remarks",
                "created_at": lead["received_at"].isoformat() if lead["received_at"] else None,
            })
    for n in notes:
        thread.append({
            "id": str(n["id"]), "body": n["body"], "author": n["author"], "source": n["source"],
            "created_at": n["created_at"].isoformat() if n["created_at"] else None,
        })
    return {"items": thread}


class NoteCreate(BaseModel):
    body: str


@router.post("/leads/{lead_id}/notes")
async def add_note(lead_id: UUID, payload: NoteCreate, user: dict = Depends(current_user)):
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="empty note")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    author = user.get("name") or user.get("email") or "You"
    async with engine.begin() as conn:
        exists = (await conn.execute(text("SELECT 1 FROM leads WHERE id = :id"), {"id": lead_id})).first()
        if exists is None:
            raise HTTPException(status_code=404, detail="lead not found")
        await conn.execute(pg_insert(LeadNote).values(lead_id=lead_id, body=body, author=author, source="note"))
    return {"status": "ok"}


# --- visit planner -------------------------------------------------------------

class VisitStop(BaseModel):
    inventory_id: int | None = None
    name: str | None = None
    society: str | None = None
    locality: str | None = None
    price_text: str | None = None
    lat: float | None = None
    lng: float | None = None


class VisitPlan(BaseModel):
    trip_date: str | None = None
    rm: str | None = None
    start_lat: float | None = None
    start_lng: float | None = None
    total_km: float | None = None
    total_min: float | None = None
    route_source: str | None = None
    stops: list[VisitStop] = []


@router.post("/leads/{lead_id}/visits")
async def save_visit(lead_id: UUID, payload: VisitPlan):
    if not payload.stops:
        raise HTTPException(status_code=422, detail="add at least one stop")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    trip = None
    if payload.trip_date:
        try:
            trip = date.fromisoformat(payload.trip_date)
        except ValueError:
            trip = None
    async with engine.begin() as conn:
        if (await conn.execute(text("SELECT 1 FROM leads WHERE id = :id"), {"id": lead_id})).first() is None:
            raise HTTPException(status_code=404, detail="lead not found")
        await conn.execute(pg_insert(Visit).values(
            lead_id=lead_id, trip_date=trip, rm=payload.rm,
            start_lat=payload.start_lat, start_lng=payload.start_lng,
            total_km=payload.total_km, total_min=payload.total_min, route_source=payload.route_source,
            stops=[s.model_dump() for s in payload.stops],
        ))
        # Saving a trip plan deliberately does NOT move the lead. A plan is internal
        # preparation, not an appointment — only a real Openhouse booking
        # (POST /v1/visits/book) sets 'visit_scheduled'. Until then the saved-plan card
        # reads "Visit not scheduled yet".
    return {"status": "ok"}


@router.get("/leads/{lead_id}/visits")
async def latest_visit(lead_id: UUID):
    engine = neon_engine()
    if engine is None:
        return {"plan": None}
    async with engine.connect() as conn:
        v = (await conn.execute(text(
            "SELECT * FROM visits WHERE lead_id = :id ORDER BY created_at DESC LIMIT 1"), {"id": lead_id})).mappings().first()
    if v is None:
        return {"plan": None}
    return {"plan": {
        "trip_date": v["trip_date"].isoformat() if v["trip_date"] else None, "rm": v["rm"],
        "start_lat": float(v["start_lat"]) if v["start_lat"] is not None else None,
        "start_lng": float(v["start_lng"]) if v["start_lng"] is not None else None,
        "total_km": float(v["total_km"]) if v["total_km"] is not None else None,
        "total_min": float(v["total_min"]) if v["total_min"] is not None else None,
        "route_source": v["route_source"], "stops": v["stops"],
        "created_at": v["created_at"].isoformat() if v["created_at"] else None,
    }}


# --- assignment ---------------------------------------------------------------

@router.get("/assignees")
async def list_assignees():
    """Active non-admin users a lead can be assigned to (admins don't work leads)."""
    engine = neon_engine()
    if engine is None:
        return {"items": []}
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT name, email FROM users WHERE active AND name IS NOT NULL AND role <> 'admin' ORDER BY name"))
        return {"items": [{"name": r[0], "email": r[1]} for r in res]}


class AssignPayload(BaseModel):
    assigned_to: str | None = None  # null → unassign


@router.post("/leads/{lead_id}/assign")
async def assign_lead(lead_id: UUID, payload: AssignPayload):
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    name = (payload.assigned_to or "").strip() or None
    async with engine.begin() as conn:
        res = await conn.execute(text("UPDATE leads SET assigned_to = :a WHERE id = :id"), {"a": name, "id": lead_id})
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
    return {"status": "ok", "assigned_to": name}


class BulkAssign(BaseModel):
    lead_ids: list[UUID]
    assigned_to: str | None = None  # null → unassign all


@router.post("/leads/bulk-assign")
async def bulk_assign(payload: BulkAssign):
    if not payload.lead_ids:
        raise HTTPException(status_code=422, detail="no leads selected")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    name = (payload.assigned_to or "").strip() or None
    async with engine.begin() as conn:
        res = await conn.execute(
            text("UPDATE leads SET assigned_to = :a WHERE id = ANY(:ids)"),
            {"a": name, "ids": payload.lead_ids},
        )
    return {"status": "ok", "updated": res.rowcount, "assigned_to": name}


# --- master_societies autocomplete -------------------------------------------

@router.get("/societies/search")
async def societies_search(q: str = Query("", min_length=0)):
    return {"items": await search_societies(q)}


@router.get("/localities/search")
async def localities_search(q: str = Query("", min_length=0)):
    return {"items": await search_localities(q)}


@router.get("/micromarkets/search")
async def micromarkets_search(q: str = Query("", min_length=0)):
    return {"items": await search_micromarkets(q)}


@router.get("/localities/by-micromarket")
async def localities_by_mm(micro_market: str = Query(...)):
    """All localities inside a micro-market (for cascade auto-populate)."""
    return {"items": await localities_in_micromarket(micro_market)}


@router.get("/societies/by-locality")
async def societies_by_locality(locality: str = Query(...)):
    """All societies inside a locality (for cascade auto-populate)."""
    return {"items": await societies_in_locality(locality)}


@router.get("/societies/by-city")
async def societies_by_city(city: str = Query(...)):
    """All societies in a city — backs the city→society cascade on the WhatsApp
    create-lead modal."""
    return {"items": await societies_in_city(city)}
