"""Automatic round-robin assignment of new leads to RMs.

Two rules, both the user's:

  * a lead whose city an RM covers goes to one of the RMs covering that city;
  * anything else — blank, a typo, a city nobody covers — goes to any RM.

A city is "valid" exactly when at least one active RM lists it in `users.city`. That
is deliberately not a second hardcoded list: adding Faridabad to an RM's array makes
Faridabad a covered city that minute, and removing the last RM who covers a city makes
its leads fall through to the whole pool instead of piling up unassigned.

**The balance is leads assigned TODAY, on the IST calendar**, not lifetime totals.
Lifetime is what hands a new joinee every lead on their first day: they start at zero
and stay bottom of the ordering until they have caught up on everybody else's history.
A daily count puts the whole team back on level footing at IST midnight, so a joinee
takes their share and no more.

Runs as an hourly sweep over `assigned_to IS NULL` rather than inline at ingest,
because it has to cover a writer that never runs any of this code: the Apps Script
INSERTs into `leads` over Neon's SQL-over-HTTP endpoint. A sweep reads the table, so it
catches every source — sheet cron, Meta webhook, WhatsApp, and that direct write.
"""
import logging

from sqlalchemy import text

from ..db import neon_engine
from . import activity

log = logging.getLogger("lead_assign")

# How many leads one tick will claim. A bound, not a fallback: the sweep assigns one at
# a time (see below), so an unbounded backlog would hold a transaction open for as many
# Singapore round trips as there are leads. Anything left over is taken next hour.
SWEEP_LIMIT = 500

# Every city at least one active RM takes. `unnest` rather than a literal list, so the
# roster is the only place coverage is defined.
COVERED_CITIES = text("""
    SELECT DISTINCT unnest(u.city) AS city
      FROM users u
     WHERE u.active AND u.role = 'rm'
""")

PICK_RM = text("""
    SELECT u.name
      FROM users u
      LEFT JOIN leads l
        ON lower(l.assigned_to) = lower(u.name)
       -- The day window lives in the JOIN, not the WHERE. An RM who has taken nothing
       -- today is precisely the RM this query exists to find, and a WHERE on a LEFT
       -- JOIN's right-hand table drops exactly those people.
       AND (l.assigned_at AT TIME ZONE 'Asia/Kolkata')::date
           = (now() AT TIME ZONE 'Asia/Kolkata')::date
     WHERE u.active
       -- exactly 'rm', deliberately NOT core.auth.CALLING_ROLES: a test_rm is dialled
       -- by campaigns but must never be handed a real buyer
       AND u.role = 'rm'
       AND u.name IS NOT NULL AND btrim(u.name) <> ''
       -- CAST because asyncpg can't infer a bare parameter's type from `IS NULL`.
       -- Case-insensitive so an admin typing "gurgaon" still matches a "Gurgaon" lead.
       AND (CAST(:city AS text) IS NULL
            OR EXISTS (SELECT 1 FROM unnest(u.city) c
                        WHERE lower(c) = lower(CAST(:city AS text))))
     GROUP BY u.name
     -- fewest today; then longest since their last lead (never-assigned sorts first
     -- via NULLS FIRST); then name, so the pick is deterministic
     ORDER BY count(l.id), max(l.assigned_at) NULLS FIRST, u.name
     LIMIT 1
""")

UNASSIGNED = text("""
    SELECT id, city FROM leads
     WHERE assigned_to IS NULL AND NOT is_test
     -- oldest first: a lead that has been waiting longest is the one costing us most
     ORDER BY received_at NULLS LAST, created_at
     LIMIT :limit
""")

# `AND assigned_to IS NULL` again, deliberately: it makes the claim a no-op if anything
# else — a human on the Leads page, a second sweep — took the lead since it was read.
CLAIM = text("""
    UPDATE leads SET assigned_to = :rm, assigned_at = now()
     WHERE id = :id AND assigned_to IS NULL
    RETURNING id
""")


async def covered_cities(conn) -> set[str]:
    """Lower-cased set of cities some active RM takes."""
    rows = await conn.execute(COVERED_CITIES)
    return {c.strip().lower() for (c,) in rows if c and c.strip()}


async def pick_rm(conn, city: str | None, covered: set[str]) -> str | None:
    """The RM who should take a lead in this city, or None if there are no active RMs.

    Passing `city=None` into PICK_RM widens the pool to every RM, which is what an
    uncovered city must do — narrowing to nobody would leave the lead unassigned
    forever, and an unworked lead is worse than a slightly uneven split.
    """
    key = (city or "").strip().lower()
    scoped = city if key and key in covered else None
    row = (await conn.execute(PICK_RM, {"city": scoped})).first()
    return row[0] if row else None


async def run_assignment_sweep(trigger: str = "cron", limit: int = SWEEP_LIMIT) -> dict:
    """Assign every unassigned lead. Safe to re-run; assigns nothing when none are waiting."""
    engine = neon_engine()
    if engine is None:
        return {"status": "not_configured", "assigned": 0, "pending": 0}

    assigned, per_rm = 0, {}
    async with engine.begin() as conn:
        leads = (await conn.execute(UNASSIGNED, {"limit": limit})).all()
        if not leads:
            return {"status": "ok", "assigned": 0, "pending": 0, "by_rm": {}}

        covered = await covered_cities(conn)

        # ONE AT A TIME, deliberately. A set-based UPDATE would evaluate every pick
        # against the same starting counts and hand the entire backlog to whichever RM
        # is currently lowest. The loop lets each pick see the previous one's effect —
        # they are in this transaction, so the count query reads its own writes.
        for lead_id, city in leads:
            rm = await pick_rm(conn, city, covered)
            if rm is None:
                log.warning("no active RM to assign lead %s (city=%r)", lead_id, city)
                break  # nobody to assign to; the rest of the batch would fail the same way
            claimed = (await conn.execute(CLAIM, {"rm": rm, "id": lead_id})).first()
            if claimed is None:
                continue  # someone else took it between the read and the write
            await activity.record(conn, activity.row_for(
                None, entity_type="lead", entity_id=lead_id,
                action="assigned", field="assigned_to", before=None, after=rm,
                metadata={"source": "auto_round_robin", "city": city, "trigger": trigger}))
            assigned += 1
            per_rm[rm] = per_rm.get(rm, 0) + 1

        pending = (await conn.execute(text(
            "SELECT count(*) FROM leads WHERE assigned_to IS NULL AND NOT is_test"))).scalar()

    log.info("lead assignment (%s): %d assigned %s, %d still unassigned",
             trigger, assigned, per_rm or "", pending)
    return {"status": "ok", "assigned": assigned, "pending": pending, "by_rm": per_rm}
