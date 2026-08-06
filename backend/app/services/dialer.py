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
from time import monotonic

from fastapi import HTTPException
from sqlalchemy import text

from ..db import neon_engine
from ..events import publish, rm_channel

log = logging.getLogger("dialer")

TICK_SECONDS = 3
# a 'dialing' row with no hangup callback by now is assumed lost — otherwise one
# dropped webhook would wedge that RM for the rest of the campaign
STALE_AFTER_SECONDS = 420
# after this long with no callback, stop waiting for one and ask Bonvoice directly.
# Callbacks are the fast path; this is what makes the dialer work without them.
POLL_AFTER_SECONDS = 20
POLL_EVERY_SECONDS = 15  # per call — the tick runs far more often than that
POLL_BATCH = 20
# event_id → when it was last asked about. Process-local and self-pruning: a lost
# entry only costs one extra request.
_polled: dict[str, float] = {}
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


"""Why a queue row was skipped before anyone could dial it.

Two different things set status='skipped': this (the lead belongs to nobody in the
pool, so it was never really part of the campaign) and Stop (it *was* targeted, we
just never reached it). Counting them together made a 4-lead test campaign report
1727 targeted, so the reason has to be distinguishable — hence a shared constant
rather than the literal repeated in the stats queries."""
UNOWNED_DETAIL = "not assigned to anyone in this pool"


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
                   SET status = 'skipped', detail = :unowned
                 WHERE campaign_id = :cid AND status = 'pending' AND rm_email IS NULL"""),
        {"cid": campaign_id, "unowned": UNOWNED_DETAIL},
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

def window_minutes(raw: str, fallback: int) -> int:
    """'HH:MM' → minutes past midnight. A malformed value falls back to the caller's
    bound, matching _in_window's "a broken window means always on"."""
    try:
        h, m = (int(x) for x in str(raw).split(":")[:2])
    except (ValueError, TypeError):
        return fallback
    return h * 60 + m


def windows_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """Do two calling windows share any minute of the day?

    Half-open on purpose: a campaign ending at 13:00 and one starting at 13:00 do
    not overlap. _in_window has no midnight wrap (start <= now <= end), so neither
    does this."""
    a0, a1 = window_minutes(a_start, 0), window_minutes(a_end, 24 * 60)
    b0, b1 = window_minutes(b_start, 0), window_minutes(b_end, 24 * 60)
    return a0 < b1 and b0 < a1


def window_has_passed(start: str, end: str, now: time | None = None) -> bool:
    """Is this calling window already over for today?

    _in_window is `start <= now <= end` with no midnight wrap, so a campaign started
    at 18:40 with a 10:00–17:00 window reaches 'running' and then dials nobody until
    tomorrow morning. Nothing surfaces that — the campaign just looks stuck — so it is
    refused at creation instead.

    A malformed window is NOT past: _in_window reads it as "always on", and rejecting
    here would block a campaign the dialer would happily run. `now` is injectable so
    this is testable without freezing the clock.
    """
    try:
        h1, m1 = (int(x) for x in str(start).split(":")[:2])
        h2, m2 = (int(x) for x in str(end).split(":")[:2])
        window_start, window_end = time(h1, m1), time(h2, m2)
    except (ValueError, TypeError):
        return False
    current = now if now is not None else datetime.now(IST).time()
    # Inverted windows are somebody else's problem — they're never "in the past",
    # they're simply never open, and _in_window already reports that.
    if window_end < window_start:
        return False
    return current > window_end


def _in_window(start: str, end: str) -> bool:
    """Calling hours are IST wall-clock. A blank or malformed window means always on."""
    try:
        h1, m1 = (int(x) for x in str(start).split(":")[:2])
        h2, m2 = (int(x) for x in str(end).split(":")[:2])
    except (ValueError, TypeError):
        return True
    now = datetime.now(IST).time()
    return time(h1, m1) <= now <= time(h2, m2)


# Mirrors _RELEASE_SLOT in routers/bonvoice.py, keyed by id rather than event_id.
# RETURNING carries the RM back so the Live Calls event can be addressed.
_POLL_CLOSE = text("""
    UPDATE dial_queue
       SET status   = CASE WHEN :ends THEN 'done' ELSE status END,
           ended_at = CASE WHEN :ends THEN now() ELSE ended_at END,
           outcome  = COALESCE(:outcome, outcome),
           answered = answered OR :answered
     WHERE id = :id AND status = 'dialing'
 RETURNING id, rm_email
""")


async def poll_open_calls(engine) -> None:
    """For calls that have been ringing a while with no callback, ask Bonvoice how they
    went and close them out.

    This is the fallback that makes the queue advance whether or not the callback URL
    is reachable. It only looks at calls older than POLL_AFTER_SECONDS, so a working
    webhook resolves almost everything before this ever runs.
    """
    from ..routers.bonvoice import fetch_call_state

    async with engine.connect() as conn:
        rows = (await conn.execute(
            text("""SELECT id, event_id FROM dial_queue
                     WHERE status = 'dialing' AND event_id IS NOT NULL
                       AND dialed_at < now() - make_interval(secs => :s)
                     ORDER BY dialed_at LIMIT :lim"""),
            {"s": POLL_AFTER_SECONDS, "lim": POLL_BATCH},
        )).mappings().all()

    now = monotonic()
    for stale_key in [k for k, t in _polled.items() if now - t > 3600]:
        _polled.pop(stale_key, None)

    for row in rows:
        if now - _polled.get(row["event_id"], 0.0) < POLL_EVERY_SECONDS:
            continue  # a 20-minute call must not mean 400 requests
        _polled[row["event_id"]] = now
        state = await fetch_call_state(row["event_id"])
        if state is None:
            continue  # couldn't tell — leave it ringing; the reaper is the backstop
        ended, answered, status = state
        if not ended and not answered:
            continue
        async with engine.begin() as conn:
            closed = (await conn.execute(
                _POLL_CLOSE,
                {"id": row["id"], "ends": ended, "answered": answered, "outcome": status},
            )).mappings().first()
        if ended:
            log.info("dialer: closed %s from the call log (answered=%s status=%s)",
                     row["event_id"], answered, status)
            # This path exists because the callback never arrived. Without the event
            # the RM's page would sit on "Ringing…" for a call that ended minutes ago.
            if closed and closed["rm_email"]:
                await publish(rm_channel(closed["rm_email"]),
                              {"type": "call_ended", "queue_item_id": str(closed["id"])})


async def tick_all() -> None:
    engine = neon_engine()
    if engine is None:
        return
    try:
        await poll_open_calls(engine)
    except Exception:  # noqa: BLE001 — polling is the fallback, never the blocker
        log.exception("dialer: polling open calls failed")
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
                           AND q.attempts < :max AND NOT q.answered
                           AND q.ended_at < now() - make_interval(mins => :cool)"""),
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
        # 'retryable' are done-but-never-connected rows still inside their cooldown —
        # they become pending again shortly, so the campaign is NOT finished. Without
        # this a multi-attempt campaign declares itself done during the cooldown gap
        # and its retries never fire.
        counts = (await conn.execute(
            text("""SELECT count(*) FILTER (WHERE status = 'pending') AS pending,
                           count(*) FILTER (WHERE status = 'done'
                                            AND attempts < :max AND NOT answered) AS retryable
                      FROM dial_queue q WHERE campaign_id = :cid"""),
            {"cid": c["id"], "max": c["max_attempts"] or 1},
        )).mappings().first()
        pending = int(counts["pending"] or 0)
        retryable = int(counts["retryable"] or 0)

    by_rm = {r["rm_email"]: r for r in load}
    if pending == 0:
        if not retryable and not any(r["live"] for r in load):
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
    from ..routers.bonvoice import _digits, new_event_id, place_bridge  # circular at import time

    # Reserved before the call is placed and stored with the claim: Bonvoice can fire
    # the hangup callback before its own HTTP response reaches us, and a slot whose
    # event_id lands late would never be released — the RM would sit on "Ringing…"
    # until the stale reaper cleared it minutes later.
    event_id = new_event_id()
    mine = "AND rm_email = :rm" if owned else ""
    async with engine.begin() as conn:
        rm = (await conn.execute(
            text("SELECT phone FROM users WHERE lower(email) = lower(:e) AND active"),
            {"e": rm_email},
        )).mappings().first()
        # FOR UPDATE SKIP LOCKED: two app instances ticking at once can't claim the
        # same lead, so nobody gets dialled twice
        item = (await conn.execute(
            # outcome/detail are cleared too: a redial that inherited the previous
            # attempt's "no callback" would report a result it hasn't got yet
            text(f"""UPDATE dial_queue
                       SET status = 'dialing', rm_email = :rm, event_id = :ev,
                           outcome = NULL, detail = NULL,
                           attempts = attempts + 1, dialed_at = now(), ended_at = NULL
                     WHERE id = (SELECT id FROM dial_queue
                                  WHERE campaign_id = :cid AND status = 'pending' {mine}
                                  ORDER BY position, id LIMIT 1 FOR UPDATE SKIP LOCKED)
                 RETURNING id, lead_id, attempts"""),
            {"cid": c["id"], "rm": rm_email, "ev": event_id},
        )).mappings().first()
        if item is None:
            return False
        lead = (await conn.execute(
            text("SELECT phone FROM leads WHERE id = :id"), {"id": item["lead_id"]}
        )).mappings().first()

    rm_phone = _digits(rm["phone"] if rm else None)
    lead_phone = _digits(lead["phone"] if lead else None)
    if not rm_phone:
        await _release(engine, item["id"], f"{rm_email} has no mobile number on file", retry=True)
        return True
    if not lead_phone:
        await _release(engine, item["id"], "lead has no usable phone number", retry=False)
        return True

    try:
        await place_bridge(rm_phone, lead_phone, {
            "lead_id": str(item["lead_id"]),
            "actor": rm_email,
            "campaign_id": str(c["id"]),
        }, event_id=event_id)
    except HTTPException as e:
        retry = item["attempts"] < (c["max_attempts"] or 1)
        await _release(engine, item["id"], str(e.detail)[:300], retry=retry)
        return True

    log.info("dialer: campaign=%s rm=%s lead=%s event=%s", c["id"], rm_email,
             item["lead_id"], event_id)
    # The handset is about to ring. This is the event the whole page exists for —
    # without it the RM answers a call with no idea who is on the other end.
    await publish(rm_channel(rm_email),
                  {"type": "call_started", "queue_item_id": str(item["id"])})
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
