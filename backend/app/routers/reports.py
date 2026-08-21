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
    # Parsed to real dates, not passed through as strings: asyncpg binds parameters
    # itself and rejects a string against a date column. Parsing here also validates
    # the querystring — a malformed date fails loudly instead of matching nothing.
    try:
        start = date.fromisoformat(date_from) if date_from else today
        end = date.fromisoformat(date_to) if date_to else start
    except ValueError:
        raise HTTPException(status_code=422, detail="dates must be YYYY-MM-DD")
    if end < start:
        raise HTTPException(status_code=422, detail="'to' is before 'from'")

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
