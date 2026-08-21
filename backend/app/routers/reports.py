"""Per-RM activity report.

Every number is derived from activity_log — which is why the events had to exist
first. Nothing here reads the leads table: counting `stage = 'qualified'` today would
tell you the current state, not who moved it or when, and a lead qualified last month
would land in today's column.

Two decisions the SQL encodes:

  * The day window lives in the JOIN, not the WHERE. An RM who did nothing today is
    the most important row in this report, and a WHERE on a LEFT JOIN's right-hand
    table silently drops exactly those people.
  * "Login" is the first ACTIVITY of the day, not the `login` event. JWTs last a week,
    so someone can work for days without signing in — their row would read blank while
    they were on the phone all morning.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from ..core.auth import current_user, is_calling_rm
from ..db import neon_engine

log = logging.getLogger("reports")
router = APIRouter(prefix="/reports", tags=["reports"])

IST = timezone(timedelta(hours=5, minutes=30))

# metric -> the predicate that counts it. Kept as data so the endpoint, any future CSV
# export and the tests all agree on what each column means.
_METRICS: dict[str, str] = {
    "calls_connected": "a.action = 'call_connected'",
    "calls_missed": "a.action = 'call_missed'",
    # Derived, not the stored `call_dialled`: Bonvoice's own connected flag isn't
    # trustworthy enough to report on, so this counts what the RM actually marked.
    # call_dialled keeps accumulating alongside, to be compared against later.
    "calls_dialled": "a.action IN ('call_connected', 'call_missed')",
    # All four are stage_changes — the destination is what tells them apart. Counting
    # the verb alone would print the same number in four columns.
    "leads_qualified": "a.action = 'stage_change' AND a.after_value = 'qualified'",
    "visit_scheduled": "a.action = 'stage_change' AND a.after_value = 'visit_scheduled'",
    "revisit_booked": "a.action = 'stage_change' AND a.after_value = 'revisit_scheduled'",
    "leads_rejected": "a.action = 'stage_change' AND a.after_value = 'rejected'",
}


def _metric_sql(metric: str) -> str:
    """`count(*) FILTER (...) AS metric` for one column."""
    return f"count(*) FILTER (WHERE {_METRICS[metric]}) AS {metric}"


# Where "All" starts. Resolved from the data rather than a hardcoded floor: a made-up
# 2020-01-01 would have the page header claim a range the log can't back. IST, like
# every other day boundary here.
EARLIEST_ACTIVITY = text(
    "SELECT min(created_at) AT TIME ZONE 'Asia/Kolkata' FROM activity_log"
)

RM_REPORT = text(f"""
    SELECT u.email, u.name, u.role,
           -- first action of the day, IST — see the module docstring on why this
           -- rather than the login event
           min(a.created_at) AS first_action_at,
           max(a.created_at) AS last_action_at,
           count(a.id)       AS total_events,
           {", ".join(_metric_sql(m) for m in _METRICS)}
      FROM users u
      LEFT JOIN activity_log a
        ON lower(a.actor_email) = lower(u.email)
       -- in the JOIN, deliberately: moving this to WHERE drops every RM who did
       -- nothing, which is the row a manager most wants to see
       AND (a.created_at AT TIME ZONE 'Asia/Kolkata')::date
           BETWEEN :date_from AND :date_to
     WHERE u.active
       AND u.role IN ('rm', 'test_rm')
       -- CAST because asyncpg can't infer a bare parameter's type from `IS NULL`
       -- alone: without it the whole statement fails with AmbiguousParameterError.
       AND (CAST(:email AS text) IS NULL OR lower(u.email) = lower(CAST(:email AS text)))
     GROUP BY u.email, u.name, u.role
     ORDER BY u.name NULLS LAST, u.email
""")


def _range(date_from: str | None, date_to: str | None) -> tuple[date, date]:
    """The IST day window, as real `date` objects.

    Parsed rather than passed through as strings: asyncpg binds parameters itself and
    rejects a string against a date column. Parsing here also validates the
    querystring — a malformed date fails loudly instead of quietly matching nothing.
    """
    today = datetime.now(IST).date()
    try:
        start = date.fromisoformat(date_from) if date_from else today
        end = date.fromisoformat(date_to) if date_to else start
    except ValueError:
        raise HTTPException(status_code=422, detail="dates must be YYYY-MM-DD")
    if end < start:
        raise HTTPException(status_code=422, detail="'to' is before 'from'")
    return start, end


def _scoped_email(user: dict, email: str | None) -> str:
    """Whose report the caller is allowed to open.

    A calling role only ever gets its own, whatever the querystring says — the drill-
    down shows named leads and the notes written on them, so this is a firmer boundary
    than the summary table's. Fails closed: an unresolvable admin request 422s rather
    than falling back to "everyone".
    """
    if is_calling_rm(user.get("role")):
        return (user.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=422, detail="email is required")
    return email.lower()


@router.get("/rm")
async def rm_report(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    all_time: bool = Query(False, alias="all"),
    user: dict = Depends(current_user),
):
    """One row per RM for an IST date range. Defaults to today.

    An RM sees only their own row; admins see everyone. Same reasoning as the call
    log — a person's own numbers are theirs to see, the league table is not.
    """
    engine = neon_engine()
    if engine is None:
        return {"items": [], "from": date_from, "to": date_to}

    today = datetime.now(IST).date()
    start, end = _range(date_from, date_to)

    scope_email = user.get("email") if is_calling_rm(user.get("role")) else None

    async with engine.connect() as conn:
        if all_time:
            # An empty log means there is no "all" — fall back to today rather than
            # inventing a range with nothing in it.
            floor = (await conn.execute(EARLIEST_ACTIVITY)).scalar()
            start = floor.date() if floor else today
            end = today

        rows = (await conn.execute(RM_REPORT, {
            "date_from": start, "date_to": end, "email": scope_email,
        })).mappings().all()

    items = []
    for r in rows:
        d = dict(r)
        for key in ("first_action_at", "last_action_at"):
            val = d.get(key)
            d[key] = val.isoformat() if isinstance(val, datetime) else None
        items.append(d)
    return {"items": items, "from": start.isoformat(), "to": end.isoformat(),
            "metrics": list(_METRICS)}


# ── per-RM drill-down ────────────────────────────────────────────────────────────
# One row per IST day the RM did something on, and one row per lead they touched on
# a given day. Unlike RM_REPORT above, the date window belongs in the WHERE here:
# there is no row to preserve for a silent day. The summary table already answers
# "who did nothing"; this page only exists where there is work to itemise.

RM_DAYS = text(f"""
    SELECT (a.created_at AT TIME ZONE 'Asia/Kolkata')::date AS day,
           min(a.created_at) AS first_action_at,
           max(a.created_at) AS last_action_at,
           count(*)          AS total_events,
           count(DISTINCT a.entity_id) FILTER (WHERE a.entity_type = 'lead')
                             AS unique_leads,
           {", ".join(_metric_sql(m) for m in _METRICS)}
      FROM activity_log a
     WHERE lower(a.actor_email) = lower(:email)
       AND (a.created_at AT TIME ZONE 'Asia/Kolkata')::date
           BETWEEN :date_from AND :date_to
     GROUP BY 1
     ORDER BY 1 DESC
""")

RM_IDENTITY = text("""
    SELECT email, name, role FROM users WHERE lower(email) = lower(:email)
""")

RM_DAY_LEADS = text(f"""
    SELECT a.entity_id AS lead_id,
           l.name, l.phone, l.city, l.source,
           l.stage AS current_stage,
           min(a.created_at) AS first_at,
           max(a.created_at) AS last_at,
           count(*)          AS total_events,
           {", ".join(_metric_sql(m) for m in _METRICS)},
           -- The day's stage journey: the first `before` and the last `after`. Has to
           -- be array_agg with an explicit ORDER BY — min()/max() would sort the
           -- stage names alphabetically, which is not the order they happened in.
           (array_agg(a.before_value ORDER BY a.created_at)
              FILTER (WHERE a.action = 'stage_change'))[1] AS from_stage,
           (array_agg(a.after_value ORDER BY a.created_at DESC)
              FILTER (WHERE a.action = 'stage_change'))[1] AS to_stage,
           (array_agg(a.metadata ->> 'note' ORDER BY a.created_at DESC)
              FILTER (WHERE a.action = 'note_added'))[1] AS note
      FROM activity_log a
      -- Cast the uuid to text, never the reverse: entity_id is TEXT and holds
      -- non-uuid keys ('leads_sheet'), and a regex guard doesn't save you because
      -- AND order in a JOIN isn't guaranteed.
      LEFT JOIN leads l ON l.id::text = a.entity_id
     WHERE lower(a.actor_email) = lower(:email)
       AND a.entity_type = 'lead'
       AND (a.created_at AT TIME ZONE 'Asia/Kolkata')::date = :day
     GROUP BY a.entity_id, l.name, l.phone, l.city, l.source, l.stage
     ORDER BY max(a.created_at) DESC
""")


def _iso(d: dict, *keys: str) -> dict:
    """ISO-ify the date/datetime columns in place — JSON carries neither."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
    return d


@router.get("/rm/days")
async def rm_days(
    email: str | None = Query(None),
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    all_time: bool = Query(False, alias="all"),
    user: dict = Depends(current_user),
):
    """One row per IST day for a single RM — the per-user detail page.

    Same metrics as the summary table, split by day instead of collapsed over the
    range, which is what makes "Login" meaningful again: the first action of *a* day
    is a real clock-in, the first action of a fortnight is not.
    """
    target = _scoped_email(user, email)
    start, end = _range(date_from, date_to)

    engine = neon_engine()
    if engine is None:
        return {"email": target, "name": None, "role": None,
                "days": [], "from": start.isoformat(), "to": end.isoformat()}

    async with engine.connect() as conn:
        if all_time:
            floor = (await conn.execute(EARLIEST_ACTIVITY)).scalar()
            start = floor.date() if floor else datetime.now(IST).date()
            end = datetime.now(IST).date()

        who = (await conn.execute(RM_IDENTITY, {"email": target})).mappings().first()
        rows = (await conn.execute(RM_DAYS, {
            "email": target, "date_from": start, "date_to": end,
        })).mappings().all()

    days = [_iso(dict(r), "day", "first_action_at", "last_action_at") for r in rows]
    return {
        "email": target,
        "name": who["name"] if who else None,
        "role": who["role"] if who else None,
        "days": days,
        "from": start.isoformat(), "to": end.isoformat(),
        "metrics": list(_METRICS),
    }


@router.get("/rm/leads")
async def rm_day_leads(
    day: str = Query(..., alias="date"),
    email: str | None = Query(None),
    user: dict = Depends(current_user),
):
    """Every lead one RM touched on one IST day, with that day's stage journey.

    `current_stage` is read from the leads table on purpose and is the one number here
    that isn't derived from the log — it answers "did this stick?", which is only a
    question because everything else on the row is historical.
    """
    target = _scoped_email(user, email)
    start, _ = _range(day, day)

    engine = neon_engine()
    if engine is None:
        return {"items": [], "date": start.isoformat(), "email": target}

    async with engine.connect() as conn:
        rows = (await conn.execute(RM_DAY_LEADS, {
            "email": target, "day": start,
        })).mappings().all()

    items = [_iso(dict(r), "first_at", "last_at") for r in rows]
    return {"items": items, "date": start.isoformat(), "email": target,
            "metrics": list(_METRICS)}
