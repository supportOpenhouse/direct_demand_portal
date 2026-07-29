"""Dashboard metrics — role-scoped aggregates over the leads spine."""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..core.auth import assignment_aliases, current_user
from ..db import neon_engine

router = APIRouter(tags=["metrics"], dependencies=[Depends(current_user)])

TERMINAL = "('won','rejected','rnr')"
# "Qualified" is now a stage, not a derived condition. Kept split by age so the
# dashboard can still show fresh-vs-ageing qualified leads.
ACTIVE_Q = "stage = 'qualified'"


@router.get("/metrics/dashboard")
async def dashboard(user: dict = Depends(current_user)):
    engine = neon_engine()
    if engine is None:
        return {"status": "not_configured"}

    # role scope: unassigned visible to admins only; RM → own, CM → all assigned
    scope, params = "TRUE", {}
    role = user.get("role")
    if role == "cm":
        scope = "assigned_to IS NOT NULL"
    elif role == "rm":
        aliases = assignment_aliases(user)
        if aliases:
            scope = "lower(assigned_to) = ANY(:aliases)"
            params["aliases"] = aliases
        else:
            scope = "false"

    async with engine.connect() as conn:
        totals = (await conn.execute(text(f"""
            SELECT
              count(*) FILTER (WHERE stage='new')                                              AS new,
              count(*) FILTER (WHERE {ACTIVE_Q})                                                AS qualified,
              count(*) FILTER (WHERE stage='visit_scheduled')                                   AS pipeline,
              count(*) FILTER (WHERE stage='won')                                               AS converted,
              count(*) FILTER (WHERE plan_to_buy='Within 30 days' AND stage NOT IN {TERMINAL})   AS immediate,
              count(*) FILTER (WHERE assigned_to IS NULL)                                        AS unassigned,
              count(*) FILTER (WHERE confirmed)                                                  AS confirmed_total,
              count(*)                                                                          AS total
            FROM leads WHERE {scope}
        """), params)).mappings().first()

        by_source = [dict(m) for m in (await conn.execute(text(
            f"SELECT source, count(*) c FROM leads WHERE {scope} GROUP BY source ORDER BY c DESC"), params)).mappings()]
        by_city = [dict(m) for m in (await conn.execute(text(
            f"SELECT COALESCE(city,'Unknown') city, count(*) c FROM leads WHERE {scope} GROUP BY city ORDER BY c DESC LIMIT 8"), params)).mappings()]
        by_stage = [dict(m) for m in (await conn.execute(text(
            f"SELECT stage, count(*) c FROM leads WHERE {scope} GROUP BY stage"), params)).mappings()]
        by_assignee = [dict(m) for m in (await conn.execute(text(
            f"SELECT COALESCE(assigned_to,'Unassigned') name, count(*) c FROM leads WHERE {scope} GROUP BY assigned_to ORDER BY c DESC LIMIT 10"), params)).mappings()]
        by_day = [{"day": m["d"], "c": m["c"]} for m in (await conn.execute(text(f"""
            SELECT to_char(date_trunc('day', received_at), 'YYYY-MM-DD') AS d, count(*) c
            FROM leads WHERE {scope} AND received_at >= now() - interval '30 days'
            GROUP BY 1 ORDER BY 1
        """), params)).mappings()]
        recent = [dict(m) for m in (await conn.execute(text(f"""
            SELECT id, name, source, city, society, stage, assigned_to, received_at
            FROM leads WHERE {scope} ORDER BY received_at DESC NULLS LAST LIMIT 8
        """), params)).mappings()]

    converted = totals["converted"] or 0
    confirmed_total = totals["confirmed_total"] or 0
    conv_rate = round(converted / confirmed_total * 100, 1) if confirmed_total else 0.0

    return {
        "status": "ok",
        "totals": {k: totals[k] for k in totals.keys()},
        "conversion_rate": conv_rate,
        "by_source": by_source,
        "by_city": by_city,
        "by_stage": by_stage,
        "by_assignee": by_assignee,
        "by_day": by_day,
        "recent": [
            {"id": str(r["id"]), "name": r["name"], "source": r["source"], "city": r["city"],
             "society": r["society"], "stage": r["stage"], "assigned_to": r["assigned_to"],
             "received_at": r["received_at"].isoformat() if r["received_at"] else None}
            for r in recent
        ],
    }
