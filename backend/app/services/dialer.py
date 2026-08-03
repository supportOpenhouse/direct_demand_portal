"""Auto-dialer — turn a campaign's rule tree into a queue, then keep every RM in the
pool on a call.

Two halves:

  * the **rule compiler** — the AND/OR tree the builder produces is untrusted input, so
    every field, operator and value goes through a whitelist and comes out as a bound
    parameter. Nothing from the client is ever interpolated into SQL.
  * the **tick** — runs every few seconds and, for each running campaign, dials the
    next lead on every RM who isn't already on a call. The Bonvoice hangup callback is
    what marks a slot done (see routers/bonvoice.py), so "as soon as the previous call
    ends" is literally that: the callback frees the slot, the next tick fills it.

Parallelism is the size of the RM pool. Click2Call rings the RM's own handset first,
so a second simultaneous call to the same RM would just ring a busy phone.
"""
import asyncio
import itertools
import logging
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import text

from ..db import neon_engine

log = logging.getLogger("dialer")

TICK_SECONDS = 3
# a 'dialing' row with no hangup callback by now is assumed lost — otherwise one
# dropped webhook would wedge that RM for the rest of the campaign
STALE_AFTER_SECONDS = 420
IST = timezone(timedelta(hours=5, minutes=30))

# ── rule compiler ────────────────────────────────────────────────────────────

# field → (SQL expression, kind). The frontend builder is driven by this same list
# via /v1/dialer/fields, so the two can't drift.
FIELDS: dict[str, dict] = {
    "society":        {"col": "l.society",        "kind": "multi",     "label": "Society"},
    "city":           {"col": "l.city",           "kind": "multi",     "label": "City"},
    "source":         {"col": "l.source",         "kind": "multi",     "label": "Lead source"},
    "stage":          {"col": "l.stage",          "kind": "multi",     "label": "Lead stage"},
    "assigned_to":    {"col": "l.assigned_to",    "kind": "multi",     "label": "Assigned to"},
    "created_at":     {"col": "l.created_at",     "kind": "daterange", "label": "Created date"},
    "miss_count":     {"col": "l.miss_count",     "kind": "number",    "label": "Missed calls"},
    "ever_connected": {"col": "l.ever_connected", "kind": "bool",      "label": "Ever connected"},
}
OPS = {
    "multi": {"IN", "NOT IN"},
    "daterange": {"BETWEEN"},
    "number": {"=", "<=", ">=", "<", ">"},
    "bool": {"IS"},
}
MAX_DEPTH = 4
MAX_VALUES = 200  # per IN list

# Never dialable, whatever the rules say: no number to ring, or a test row.
BASE_PREDICATE = "l.phone IS NOT NULL AND btrim(l.phone) <> '' AND l.is_test = false"


def compile_rules(node: dict) -> tuple[str, dict]:
    """Rule tree → (SQL boolean expression over alias `l`, bound params).

    Raises ValueError on anything not in the whitelist. An empty condition means
    "no filter" and compiles to TRUE, matching the builder's own preview.
    """
    params: dict = {}
    sql = _node(node, params, itertools.count(), 0)
    return sql, params


def _node(n, params: dict, ctr, depth: int) -> str:
    if depth > MAX_DEPTH:
        raise ValueError("rule tree is nested too deep")
    if not isinstance(n, dict):
        raise ValueError("bad rule node")
    if n.get("type") != "group":
        return _condition(n, params, ctr)

    combinator = n.get("combinator", "AND")
    if combinator not in ("AND", "OR"):
        raise ValueError(f"bad combinator {combinator!r}")
    children = n.get("children") or []
    if not isinstance(children, list):
        raise ValueError("group children must be a list")
    if not children:
        return "TRUE"
    parts = [_node(c, params, ctr, depth + 1) for c in children]
    return "(" + f" {combinator} ".join(parts) + ")"


def _condition(n, params: dict, ctr) -> str:
    field = FIELDS.get(n.get("field"))
    if field is None:
        raise ValueError(f"unknown field {n.get('field')!r}")
    op, kind, col = n.get("op"), field["kind"], field["col"]
    if op not in OPS[kind]:
        raise ValueError(f"operator {op!r} isn't allowed on {n.get('field')!r}")
    value = n.get("value")

    def bind(v) -> str:
        key = f"r{next(ctr)}"
        params[key] = v
        return f":{key}"

    if kind == "multi":
        if not isinstance(value, list):
            raise ValueError("a multi-select value must be a list")
        vals = [str(v) for v in value if v not in (None, "")][:MAX_VALUES]
        if not vals:
            return "TRUE"  # nothing selected = no filter, same as the live preview
        placeholders = ", ".join(bind(v) for v in vals)
        if op == "IN":
            return f"{col} IN ({placeholders})"
        # NULL NOT IN (...) is UNKNOWN in SQL but "not one of them" to a human
        return f"({col} IS NULL OR {col} NOT IN ({placeholders}))"

    if kind == "daterange":
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("a date range needs exactly two values")
        start, end = value
        if not start or not end:
            return "TRUE"
        # end is inclusive of the whole day the user picked
        return f"({col} >= {bind(str(start))}::date AND {col} < {bind(str(end))}::date + 1)"

    if kind == "number":
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise ValueError("a number condition needs a numeric value")
        return f"COALESCE({col}, 0) {op} {bind(num)}"

    return f"{col} IS {'TRUE' if bool(value) else 'NOT TRUE'}"


async def count_matching(rules: dict, owner_aliases: list[str] | None = None) -> int:
    """How many leads the rule tree selects right now.

    `owner_aliases` narrows that to leads owned by a specific pool — under the
    'assigned' strategy the rest are never dialled, so counting them would overstate
    the campaign.
    """
    engine = neon_engine()
    if engine is None:
        return 0
    where, params = compile_rules(rules)
    owned = ""
    if owner_aliases:
        owned = " AND lower(btrim(l.assigned_to)) = ANY(:owner_aliases)"
        params = {**params, "owner_aliases": owner_aliases}
    async with engine.connect() as conn:
        return int((await conn.execute(
            text(f"SELECT count(*) FROM leads l WHERE {BASE_PREDICATE} AND {where}{owned}"), params
        )).scalar() or 0)


def aliases_for(name: str | None, assignment_name: str | None) -> list[str]:
    """The names a user answers to in `leads.assigned_to`, lowercased.

    That column is free text and diverges by source — the sheet writes first names
    ('Saumya'), the in-app Assign button writes full names ('Saumya Behera') — so an
    owner is matched on their full name, their first name, and their assignment_name.
    """
    out = set()
    full = (name or "").strip()
    if full:
        out.update({full.lower(), full.split()[0].lower()})
    an = (assignment_name or "").strip()
    if an:
        out.add(an.lower())
    return sorted(out)


async def assign_owners(conn, campaign_id, owners: list[tuple[str, list[str]]]) -> int:
    """Strategy 'assigned': stamp each queued lead with the RM it already belongs to.

    Leads owned by nobody in the pool are skipped outright rather than left pending —
    a queue nobody is allowed to claim would never drain. Returns how many were skipped.
    """
    for email, aliases in owners:
        if not aliases:
            continue
        await conn.execute(
            text("""UPDATE dial_queue q SET rm_email = :rm
                      FROM leads l
                     WHERE l.id = q.lead_id AND q.campaign_id = :cid
                       AND q.rm_email IS NULL
                       AND lower(btrim(l.assigned_to)) = ANY(:aliases)"""),
            {"cid": campaign_id, "rm": email, "aliases": aliases},
        )
    skipped = await conn.execute(
        text("""UPDATE dial_queue
                   SET status = 'skipped', detail = 'not assigned to anyone in this pool'
                 WHERE campaign_id = :cid AND status = 'pending' AND rm_email IS NULL"""),
        {"cid": campaign_id},
    )
    return skipped.rowcount or 0


async def materialize(conn, campaign_id, rules: dict) -> int:
    """Freeze the rule tree into queue rows. Newest leads first; re-running can't
    duplicate a lead's slot."""
    where, params = compile_rules(rules)
    result = await conn.execute(
        text(f"""
            INSERT INTO dial_queue (id, campaign_id, lead_id, position, status)
            SELECT gen_random_uuid(), :cid, l.id,
                   row_number() OVER (ORDER BY l.created_at DESC), 'pending'
              FROM leads l
             WHERE {BASE_PREDICATE} AND {where}
            ON CONFLICT (campaign_id, lead_id) DO NOTHING
        """),
        {**params, "cid": campaign_id},
    )
    return result.rowcount or 0


# ── the tick ─────────────────────────────────────────────────────────────────

def _in_window(start: str, end: str) -> bool:
    """Calling hours are IST wall-clock. A blank or malformed window means always on."""
    try:
        h1, m1 = (int(x) for x in str(start).split(":")[:2])
        h2, m2 = (int(x) for x in str(end).split(":")[:2])
    except (ValueError, TypeError):
        return True
    now = datetime.now(IST).time()
    return time(h1, m1) <= now <= time(h2, m2)


async def tick_all() -> None:
    engine = neon_engine()
    if engine is None:
        return
    async with engine.begin() as conn:
        await conn.execute(
            text("""UPDATE dial_queue
                       SET status = 'done', ended_at = now(),
                           outcome = COALESCE(outcome, 'no callback')
                     WHERE status = 'dialing'
                       AND dialed_at < now() - make_interval(secs => :s)"""),
            {"s": STALE_AFTER_SECONDS},
        )
        campaigns = (await conn.execute(
            text("SELECT * FROM dial_campaigns WHERE status = 'running'")
        )).mappings().all()

    for c in campaigns:
        try:
            await _tick_campaign(engine, dict(c))
        except Exception:  # noqa: BLE001 — one bad campaign must not stop the rest
            log.exception("dialer: campaign %s tick failed", c["id"])


async def _tick_campaign(engine, c: dict) -> None:
    rms = [e for e in (c.get("rms") or []) if isinstance(e, str) and e]
    if not rms:
        return

    async with engine.begin() as conn:
        # leads that rang out without ever connecting get another turn, at the back of
        # the queue, once their cooldown has passed
        if (c["max_attempts"] or 1) > 1:
            await conn.execute(
                # rm_email survives the requeue — under 'assigned' it's the only thing
                # that lets the lead's own RM claim it again
                text("""UPDATE dial_queue q
                           SET status = 'pending', event_id = NULL,
                               position = position + 1000000
                         WHERE q.campaign_id = :cid AND q.status = 'done'
                           AND q.attempts < :max
                           AND q.ended_at < now() - make_interval(mins => :cool)
                           AND NOT EXISTS (SELECT 1 FROM call_logs cl
                                            WHERE cl.event_id = q.event_id AND cl.answered)"""),
                {"cid": c["id"], "max": c["max_attempts"], "cool": c["cooldown_minutes"] or 0},
            )
        load = (await conn.execute(
            text("""SELECT rm_email,
                           count(*) FILTER (WHERE status = 'dialing')          AS live,
                           count(*) FILTER (WHERE status IN ('done','failed')) AS done,
                           max(ended_at)                                       AS last_end
                      FROM dial_queue
                     WHERE campaign_id = :cid AND rm_email IS NOT NULL
                     GROUP BY rm_email"""),
            {"cid": c["id"]},
        )).mappings().all()
        pending = int((await conn.execute(
            text("SELECT count(*) FROM dial_queue WHERE campaign_id = :cid AND status = 'pending'"),
            {"cid": c["id"]},
        )).scalar() or 0)

    by_rm = {r["rm_email"]: r for r in load}
    if pending == 0:
        if not any(r["live"] for r in load):
            async with engine.begin() as conn:
                await conn.execute(
                    text("UPDATE dial_campaigns SET status = 'done' WHERE id = :cid"),
                    {"cid": c["id"]},
                )
            log.info("dialer: campaign %s finished", c["id"])
        return

    if not _in_window(c["window_start"], c["window_end"]):
        return

    now, gap = datetime.now(timezone.utc), c["gap_seconds"] or 0
    free = []
    for email in rms:
        r = by_rm.get(email)
        if r is None:
            free.append(email)
            continue
        if r["live"]:
            continue  # one live call per handset, always
        if gap and r["last_end"] and (now - r["last_end"]).total_seconds() < gap:
            continue  # still inside the pause the campaign asked for
        free.append(email)

    # Only matters when free RMs outnumber remaining leads — it decides who gets them.
    # Under 'assigned' it decides nothing: every lead already has an owner.
    epoch = datetime.fromtimestamp(0, timezone.utc)
    if c["strategy"] == "least_load":
        free.sort(key=lambda e: by_rm[e]["done"] if e in by_rm else 0)
    else:  # round-robin: longest idle goes first
        free.sort(key=lambda e: (by_rm[e]["last_end"] or epoch) if e in by_rm else epoch)

    owned = c["strategy"] == "assigned"
    for email in free:
        # No early exit: under 'assigned' one RM running dry says nothing about the rest
        await _dial_next(engine, c, email, owned)


async def _dial_next(engine, c: dict, rm_email: str, owned: bool) -> bool:
    """Claim the next pending lead for this RM and ring them. False = nothing left.

    `owned` restricts the claim to leads already stamped with this RM — that's the
    whole of the 'assigned' strategy.
    """
    mine = "AND rm_email = :rm" if owned else ""
    async with engine.begin() as conn:
        rm = (await conn.execute(
            text("SELECT phone FROM users WHERE lower(email) = lower(:e) AND active"),
            {"e": rm_email},
        )).mappings().first()
        # FOR UPDATE SKIP LOCKED: two app instances ticking at once can't claim the
        # same lead, so nobody gets dialled twice
        item = (await conn.execute(
            text(f"""UPDATE dial_queue
                       SET status = 'dialing', rm_email = :rm,
                           attempts = attempts + 1, dialed_at = now(), ended_at = NULL
                     WHERE id = (SELECT id FROM dial_queue
                                  WHERE campaign_id = :cid AND status = 'pending' {mine}
                                  ORDER BY position, id LIMIT 1 FOR UPDATE SKIP LOCKED)
                 RETURNING id, lead_id, attempts"""),
            {"cid": c["id"], "rm": rm_email},
        )).mappings().first()
        if item is None:
            return False
        lead = (await conn.execute(
            text("SELECT phone FROM leads WHERE id = :id"), {"id": item["lead_id"]}
        )).mappings().first()

    from ..routers.bonvoice import _digits, place_bridge  # circular at import time

    rm_phone = _digits(rm["phone"] if rm else None)
    lead_phone = _digits(lead["phone"] if lead else None)
    if not rm_phone:
        await _release(engine, item["id"], f"{rm_email} has no mobile number on file", retry=True)
        return True
    if not lead_phone:
        await _release(engine, item["id"], "lead has no usable phone number", retry=False)
        return True

    try:
        event_id = await place_bridge(rm_phone, lead_phone, {
            "lead_id": str(item["lead_id"]),
            "actor": rm_email,
            "campaign_id": str(c["id"]),
        })
    except HTTPException as e:
        retry = item["attempts"] < (c["max_attempts"] or 1)
        await _release(engine, item["id"], str(e.detail)[:300], retry=retry)
        return True

    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE dial_queue SET event_id = :ev WHERE id = :id"),
            {"ev": event_id, "id": item["id"]},
        )
    log.info("dialer: campaign=%s rm=%s lead=%s event=%s", c["id"], rm_email,
             item["lead_id"], event_id)
    return True


async def _release(engine, item_id, detail: str, retry: bool) -> None:
    """The call was never placed — put the slot back or mark it failed."""
    async with engine.begin() as conn:
        await conn.execute(
            text("""UPDATE dial_queue
                       SET status = CASE WHEN :retry THEN 'pending' ELSE 'failed' END,
                           detail = :detail,
                           ended_at = CASE WHEN :retry THEN NULL ELSE now() END,
                           position = position + CASE WHEN :retry THEN 1000000 ELSE 0 END
                     WHERE id = :id"""),
            {"id": item_id, "detail": detail, "retry": retry},
        )
    log.warning("dialer: dial not placed (%s) — %s", "requeued" if retry else "failed", detail)


# ── loop ─────────────────────────────────────────────────────────────────────

_task: asyncio.Task | None = None


async def _loop() -> None:
    from ..cache import try_acquire_lock

    while True:
        try:
            # One instance dials per tick. The DB claim already stops two instances
            # taking the same lead, but not two of them ringing the same RM at once.
            if await try_acquire_lock("dialer_tick", TICK_SECONDS * 3) is not None:
                await tick_all()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the loop must survive anything
            log.exception("dialer: tick failed")
        await asyncio.sleep(TICK_SECONDS)


def start_dialer() -> None:
    global _task
    if _task is None:
        _task = asyncio.create_task(_loop())
        log.info("auto-dialer loop started (every %ds)", TICK_SECONDS)


def stop_dialer() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
