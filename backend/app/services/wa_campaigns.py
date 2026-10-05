"""WhatsApp template campaigns — DB side: lists, drafts, sending, tracking, auto runs.
Spec: docs/superpowers/specs/2026-09-29-whatsapp-template-campaigns-design.md"""
import asyncio
import base64
import logging
import time
import uuid
from datetime import date, timedelta

from sqlalchemy import select, text

from ..config import get_settings
from ..db import neon_engine
from ..models import WaAutoCampaign, WaCampaign, WaCampaignRecipient, WaMessage, WaTemplate
from . import activity, gupshup_template, wa_assign
from .gupshup_events import CAMPAIGN_STOP_CODES, event_code, event_error, event_ids
from .wa_recipients import Candidate, build, flatten_param, parse_paste, parse_upload
from .wa_templates import render

log = logging.getLogger("wa_campaigns")


class NotFound(Exception):
    """A template, or a campaign to repeat, that doesn't exist → 404. Deliberately NOT a LookupError:
    IndexError and KeyError are LookupErrors, so a router catching that turns a real bug into a 'not found'."""


# Why a number is left out of a list, checked at build time (spec §5.1 step 4 / §7.2).
# Lead phones are normalised ONCE (lp) and hash-joined: an EXISTS inside a CASE runs as a
# per-row SubPlan, i.e. a regex over every lead for every uploaded phone — a 5k-row list
# against ~4k leads is 20M regex calls and a preview that times out.
EXCLUDE_SQL = text("""
    WITH p AS (SELECT DISTINCT unnest(CAST(:phones AS text[])) AS phone10),
         lp AS (SELECT DISTINCT right(regexp_replace(l.phone, '\\D', '', 'g'), 10) AS phone10 FROM leads l)
    SELECT p.phone10,
           CASE
             WHEN c.tag = 'opted_out' THEN 'opted_out'
             WHEN c.tag = 'rejected'  THEN 'rejected'
             WHEN lp.phone10 IS NOT NULL AND CAST(:skip_leads AS boolean) THEN 'is_lead'
             -- Gupshup 1002 = no WhatsApp account: permanent, never send again (contract §8).
             -- error is '<code>: <reason>' (Task 9) — match the code, never the reason text.
             WHEN EXISTS (SELECT 1 FROM wa_campaign_recipients r
                           WHERE r.phone10 = p.phone10 AND r.status = 'failed'
                             AND split_part(r.error, ':', 1) = '1002') THEN 'no_whatsapp'
             WHEN EXISTS (SELECT 1 FROM wa_campaign_recipients r
                           WHERE r.phone10 = p.phone10
                             AND r.sent_at > (now() - make_interval(days => :cooldown_days))
                             AND NOT (r.campaign_id = ANY(CAST(:ignore_campaigns AS uuid[])))) THEN 'cooldown'
           END AS reason
      FROM p LEFT JOIN wa_contacts c ON c.phone10 = p.phone10
             LEFT JOIN lp ON lp.phone10 = p.phone10
""")

# Source "existing WhatsApp contacts": numbers that wrote to us, have no lead, aren't
# rejected / opted out. One row per number, NEWEST FIRST (who wrote last is who is messaged
# first under the daily cap); name = sender name off their newest inbound message.
# Hands back the FULL stored phone, not its last 10 digits: build() validates it as exactly
# one Indian mobile, so a +44 number is refused instead of being sliced into a stranger's.
# DISTINCT ON forces its own ORDER BY (the number), hence the wrapper that sorts by recency.
WA_CONTACTS_SQL = text("""
    SELECT phone, name FROM (
        SELECT DISTINCT ON (right(m.phone, 10)) m.phone AS phone, m.name, m.created_at AS last_at
          FROM wa_messages m
          LEFT JOIN wa_contacts c ON c.phone10 = right(m.phone, 10)
         WHERE m.direction = 'in'
           AND (c.tag IS NULL OR c.tag NOT IN ('rejected', 'opted_out'))
           AND NOT EXISTS (SELECT 1 FROM leads l
                            WHERE right(regexp_replace(l.phone, '\\D', '', 'g'), 10) = right(m.phone, 10))
         ORDER BY right(m.phone, 10), m.created_at DESC
    ) newest
    ORDER BY last_at DESC, phone
""")

# Source "repeat a previous list": that campaign's recipients, in LIST ORDER (position — ids are
# random uuids, so without it the order is arbitrary). In non_responders mode, drop anyone with
# an inbound message after their own send.
# Never repeat to a number Gupshup/Meta already refused for good: 1002 no WhatsApp,
# 131026 undeliverable, 131050 / 1012 opted out (contract §3.5, §7, §8). By CODE —
# the reason text varies. A per-row manual Retry is still possible (Task 16 decides).
# The COALESCE matters: a failed row with NO error text makes the IN() NULL, and NOT (true AND
# NULL) is NULL — which WHERE reads as false, silently dropping that recipient from the repeat.
REPEAT_SQL = text("""
    SELECT r.phone10, r.name, r.variables
      FROM wa_campaign_recipients r
     WHERE r.campaign_id = :campaign_id
       AND r.status <> 'skipped'
       AND (:mode = 'everyone' OR NOT EXISTS (
             SELECT 1 FROM wa_messages m
              WHERE right(m.phone, 10) = r.phone10 AND m.direction = 'in'
                AND r.sent_at IS NOT NULL AND m.created_at > r.sent_at))
       AND NOT (r.status = 'failed'
                AND COALESCE(split_part(r.error, ':', 1) IN ('1002', '131026', '131050', '1012'), false))
     ORDER BY r.position, r.id
""")

# The campaign being repeated, with the slot count of the template it was sent with: a list built
# for N variables can't be dropped into a template that has a different count (spec §5.1).
SOURCE_CAMPAIGN_SQL = text("""
    SELECT c.id, t.variable_count
      FROM wa_campaigns c JOIN wa_templates t ON t.id = c.template_id
     WHERE c.id = :campaign_id
""")

# The campaigns a repeat may re-message without tripping cooldown: the whole tree its source belongs to
# (walk repeat_of up to the root, then every descendant of the root). Auto runs set repeat_of too, so this
# also covers an auto campaign's seed and runs (spec §4.4, §10: repeating a list is the point).
# `up` is a plain UNION: it discards a row it has already produced, so a hand-made cycle in repeat_of
# (raw SQL only) ends instead of looping forever. `down` stays UNION ALL — it only descends from a root.
REPEAT_FAMILY_SQL = text("""
    WITH RECURSIVE up AS (
        SELECT id, repeat_of FROM wa_campaigns WHERE id = :src
        UNION
        SELECT c.id, c.repeat_of FROM wa_campaigns c JOIN up ON c.id = up.repeat_of
    ), down AS (
        SELECT id FROM up WHERE repeat_of IS NULL
        UNION ALL
        SELECT c.id FROM wa_campaigns c JOIN down ON c.repeat_of = down.id
    )
    SELECT id FROM down
""")


def read_upload(file_name: str | None, file_b64: str | None) -> tuple[list[str], list[list[str]]]:
    """The uploaded file's (headers, rows). ValueError (→ 422) when it can't be read."""
    try:
        return parse_upload(file_name or "list.csv", base64.b64decode(file_b64 or "", validate=True))
    except Exception as e:  # noqa: BLE001 — bad base64, a corrupt .xlsx, a renamed .pdf: all "can't read it"
        raise ValueError(f"couldn't read that file — upload a .csv or .xlsx ({type(e).__name__})") from e


async def candidates_for(conn, req) -> tuple[list[Candidate], dict, list[str]]:
    """(candidates, template row, headers) for any of the four sources."""
    # Checked first, and here rather than only in the preview endpoint: POST /wa-campaigns
    # reaches this too, and a repeat that names no campaign would otherwise save an empty draft.
    if req.source == "repeat" and not req.repeat_of:
        raise ValueError("pick the campaign whose list to repeat")
    t = (await conn.execute(select(WaTemplate.__table__).where(WaTemplate.id == req.template_id))).mappings().first()
    if t is None:
        raise NotFound("template not found")
    n, defaults = t["variable_count"], list(t["variable_defaults"] or [None] * t["variable_count"])
    var_cols = (list(req.var_cols) + [None] * n)[:n]
    fixed = (list(req.fixed) + [None] * n)[:n]
    headers: list[str] = []
    if req.source == "upload":
        # Off the event loop: parsing a 200k-row .xlsx blocks for seconds, and this is the one process
        # that also serves the webhooks and the dialer.
        headers, rows = await asyncio.to_thread(read_upload, req.file_name, req.file_b64)
        cands = build(rows, phone_col=req.phone_col, name_col=req.name_col, var_cols=var_cols, fixed=fixed, defaults=defaults)
    elif req.source == "paste":
        rows = parse_paste(req.paste or "")
        cands = build(rows, phone_col=0, name_col=req.name_col, var_cols=var_cols, fixed=fixed, defaults=defaults)
    elif req.source == "wa_contacts":
        # contact rows: [phone, name] — the FULL stored phone, so a +44 number is refused by build()
        # instead of sliced into someone's Indian mobile; a slot can map to the name (col 1) or a fixed value
        rows = [[r["phone"], r["name"] or ""] for r in (await conn.execute(WA_CONTACTS_SQL)).mappings()]
        cands = build(rows, phone_col=0, name_col=1, var_cols=var_cols, fixed=fixed, defaults=defaults)
    else:  # repeat
        src = (await conn.execute(SOURCE_CAMPAIGN_SQL, {"campaign_id": req.repeat_of})).mappings().first()
        if src is None:
            raise NotFound("campaign to repeat not found")
        if src["variable_count"] != n:
            # padding / truncating by position would shift every variable into the wrong slot
            k = src["variable_count"]
            raise ValueError(f"That list was sent with a template that has {k} variable{'' if k == 1 else 's'} — "
                             f"pick a template with {k}, or upload the list again")
        rows = (await conn.execute(REPEAT_SQL, {"campaign_id": req.repeat_of, "mode": req.repeat_mode})).mappings().all()
        cands = []
        for r in rows:
            vals = list(r["variables"] or [])
            vals = (vals + [None] * n)[:n]
            # flatten what a default fills in: a default with a newline would fail every row at Meta (132018)
            vals = [flatten_param(v or defaults[i]) for i, v in enumerate(vals)]
            cands.append(Candidate(r["phone10"], r["name"], vals, "missing_variable" if None in vals else None))
    return cands, dict(t), headers


async def ignore_for(conn, req) -> list:
    """Cooldown exemptions: the source's whole repeat tree for a repeat; nothing for a fresh list
    (a stray repeat_of on a paste or an upload must not lift anyone's cooldown). One helper for the
    preview AND the draft, so the two can't disagree about who is blocked."""
    if req.source != "repeat" or not req.repeat_of:
        return []
    return [r[0] for r in await conn.execute(REPEAT_FAMILY_SQL, {"src": req.repeat_of})]


async def classify(conn, cands: list[Candidate], *, cooldown_days: int, ignore_campaigns: list[uuid.UUID],
                   skip_leads: bool = True) -> list[dict]:
    phones = [c.phone10 for c in cands if c.phone10 and c.error is None]
    reasons = {}
    if phones:
        res = await conn.execute(EXCLUDE_SQL, {"phones": phones, "cooldown_days": cooldown_days,
                                               "ignore_campaigns": list(ignore_campaigns),  # uuid.UUID objects
                                               "skip_leads": skip_leads})
        reasons = {r[0]: r[1] for r in res if r[1]}
    out = []
    for c in cands:
        if c.error:
            out.append({"phone10": c.phone10, "name": c.name, "variables": c.variables,
                        "status": "duplicate" if c.error == "duplicate" else "invalid", "reason": c.error})
        elif c.phone10 in reasons:
            out.append({"phone10": c.phone10, "name": c.name, "variables": c.variables,
                        "status": "skipped", "reason": reasons[c.phone10]})
        else:
            out.append({"phone10": c.phone10, "name": c.name, "variables": c.variables,
                        "status": "valid", "reason": None})
    return out


def counts(rows: list[dict]) -> dict:
    out = {"valid": 0, "invalid": 0, "duplicate": 0, "skipped": 0}
    for r in rows:
        out[r["status"]] += 1
    return out


def samples(template: dict, rows: list[dict], k: int = 5) -> list[str]:
    return [render(template["body"], [str(v) for v in r["variables"]])
            for r in rows if r["status"] == "valid"][:k]


async def create_draft(conn, req, user: dict) -> uuid.UUID:
    cands, t, _ = await candidates_for(conn, req)
    if not t["active"]:
        raise ValueError("that template is inactive")
    rows = await classify(conn, cands, cooldown_days=req.cooldown_days,
                          ignore_campaigns=await ignore_for(conn, req))
    # A draft needs at least one VALID number. Skip verdicts are frozen at build time, so a list whose every
    # row was skipped (opted out, rejected, a lead, not on WhatsApp, in cooldown) would save with 0 queued and
    # could never send — refuse it exactly like an all-invalid one.
    if not any(r["status"] == "valid" for r in rows):
        raise ValueError("Nothing to send — no number in this list can be messaged "
                         "(all invalid, duplicates, or skipped; see the preview for why)")
    keep = [r for r in rows if r["status"] in ("valid", "skipped")]
    cid = uuid.uuid4()
    await conn.execute(WaCampaign.__table__.insert().values(
        id=cid, name=req.name.strip(), template_id=req.template_id, source=req.source,
        repeat_of=req.repeat_of if req.source == "repeat" else None, status="draft",
        created_by=user.get("email") or "admin", send_window_start=req.send_window_start,
        send_window_end=req.send_window_end, rate_per_minute=req.rate_per_minute))
    # position = list order, so a repeat (and the send loop) can keep it: ids are random uuids
    await conn.execute(WaCampaignRecipient.__table__.insert(), [{
        "id": uuid.uuid4(), "campaign_id": cid, "phone10": r["phone10"], "name": r["name"],
        "variables": r["variables"], "status": "queued" if r["status"] == "valid" else "skipped",
        "skip_reason": r["reason"] if r["status"] == "skipped" else None, "position": i}
        for i, r in enumerate(keep)])
    await activity.record(conn, activity.row_for(
        activity.Actor.of(user), entity_type="wa_campaign", entity_id=str(cid), action="wa_campaign_created",
        metadata={"name": req.name, "source": req.source, "queued": sum(r["status"] == "valid" for r in keep),
                  "skipped": sum(r["status"] == "skipped" for r in keep)}))
    return cid


# The funnel for a list of campaigns, computed from their recipients — never stored, so it can't drift (spec §4.2).
# `accepted` = Gupshup took the send (2xx) and no `sent` receipt has arrived yet; `sent` ⊇ `delivered` ⊇ `read`;
# `unknown` = rows stuck in `submitted` (claimed, the outcome never recorded).
# `replied`: a reply is credited to the most recent campaign send before it (spec §2) — an inbound message after this
# row's send, with no later send to the same number in between.
FUNNEL_SQL = text("""
    SELECT r.campaign_id,
           count(*)                                              AS recipients,
           count(*) FILTER (WHERE r.status = 'queued')           AS queued,
           count(*) FILTER (WHERE r.status = 'accepted')         AS accepted,
           count(*) FILTER (WHERE r.status IN ('sent','delivered','read')) AS sent,
           count(*) FILTER (WHERE r.status IN ('delivered','read'))        AS delivered,
           count(*) FILTER (WHERE r.status = 'read')             AS read,
           count(*) FILTER (WHERE r.status = 'failed')           AS failed,
           count(*) FILTER (WHERE r.status = 'skipped')          AS skipped,
           count(*) FILTER (WHERE r.status = 'submitted')        AS unknown,
           count(*) FILTER (WHERE EXISTS (
               SELECT 1 FROM wa_messages m
                WHERE right(m.phone, 10) = r.phone10 AND m.direction = 'in'
                  AND r.sent_at IS NOT NULL AND m.created_at > r.sent_at
                  AND NOT EXISTS (SELECT 1 FROM wa_campaign_recipients r2
                                   WHERE r2.phone10 = r.phone10
                                     AND r2.sent_at > r.sent_at AND r2.sent_at < m.created_at))) AS replied
      FROM wa_campaign_recipients r
     WHERE r.campaign_id = ANY(:ids)
     GROUP BY r.campaign_id
""")


# ── The send loop (spec §5.2) ─────────────────────────────────────────────────────
TICK_SECONDS = 5
BACKOFF_SECONDS = 60  # after a Gupshup 429/5xx (contract Delta 10)
# Meta's messaging limit = unique people over a MOVING 24 h, portfolio-wide (contract §9,
# Delta 16) — a calendar-day count lets 18:00 + 10:00 sends double it inside Meta's window.
SENT_24H_SQL = text("""
    SELECT count(DISTINCT phone10) FROM wa_campaign_recipients
     WHERE sent_at > now() - interval '24 hours'
""")
DUE_SQL = text("""
    SELECT c.id, c.rate_per_minute, t.gupshup_template_id, t.body, t.name AS template_name, c.created_by
      FROM wa_campaigns c JOIN wa_templates t ON t.id = c.template_id
     WHERE c.status = 'sending'
       AND to_char(now() AT TIME ZONE 'Asia/Kolkata', 'HH24:MI') >= c.send_window_start
       AND to_char(now() AT TIME ZONE 'Asia/Kolkata', 'HH24:MI') <  c.send_window_end
     ORDER BY c.launched_at
""")
NEXT_QUEUED_SQL = text("""
    SELECT id FROM wa_campaign_recipients
     WHERE campaign_id = :cid AND status = 'queued' ORDER BY position, id LIMIT :n  -- the list's own order
""")
# Opt-outs are re-checked at SEND time, not only when the list was built (Meta: honour opt-outs). Someone who
# replied STOP or stopped offers in WhatsApp after the draft was saved must not get it; nor a number marked
# rejected since. Runs in the claim's transaction, just before CLAIM_SQL (which then finds the row no longer queued).
# ponytail: cooldown is still only checked at build time — two drafts built before either sends can both reach a
# number. A send-time cooldown needs the campaign's cooldown_days stored; add it when that bites.
SKIP_OPTED_OUT_SQL = text("""
    UPDATE wa_campaign_recipients r SET status = 'skipped', skip_reason = c.tag, status_at = now()
      FROM wa_contacts c
     WHERE r.id = :id AND r.status = 'queued'
       AND c.phone10 = r.phone10 AND c.tag IN ('opted_out', 'rejected')
""")
CLAIM_SQL = text("""
    UPDATE wa_campaign_recipients SET status = 'submitted', status_at = now()
     WHERE id = :id AND status = 'queued'
    RETURNING id, phone10, variables
""")
SET_OWNER_SQL = text("UPDATE wa_campaign_recipients SET owner = :o WHERE id = :id")
# Gupshup took it (2xx + messageId): 'accepted', not 'sent' — the sent receipt moves it on (Task 9).
ACCEPTED_SQL = text("""
    UPDATE wa_campaign_recipients
       SET status = 'accepted', gupshup_id = :g, whatsapp_id = NULL, sent_at = now(), status_at = now()
     WHERE id = :id AND status = 'submitted'
""")
# Gupshup refused with 429/5xx: nothing was sent, so the row goes back in line.
REQUEUE_SQL = text("""
    UPDATE wa_campaign_recipients SET status = 'queued', status_at = now()
     WHERE id = :id AND status = 'submitted'
""")
FAILED_SQL = text("""
    UPDATE wa_campaign_recipients SET status = 'failed', error = :e, status_at = now()
     WHERE id = :id AND status = 'submitted'
""")
FINISH_SQL = text("""
    UPDATE wa_campaigns SET status = 'done', finished_at = now()
     WHERE id = :cid AND status = 'sending'
       AND NOT EXISTS (SELECT 1 FROM wa_campaign_recipients
                        WHERE campaign_id = :cid AND status = 'queued')
""")


_backoff_until = 0.0
_carry: dict = {}  # campaign id -> the fraction of a send already earned (30/min = 2.5 per tick)


def _quota(cid, rate_per_minute: int) -> int:
    """How many sends this campaign has earned this tick. Rounding per tick would give 24/min for a setting of
    30 and 12/min for a setting of 1; carrying the remainder keeps the long-run rate at what was asked."""
    earned = _carry.get(cid, 0.0) + rate_per_minute * TICK_SECONDS / 60
    n = int(earned)
    _carry[cid] = earned - n
    return n


async def tick() -> int:
    """One pass of the send loop. Returns how many recipients it attempted."""
    global _backoff_until
    s = get_settings()
    engine = neon_engine()
    if engine is None or not s.gupshup_template_configured:
        return 0  # rows stay queued until the template app is configured
    if time.monotonic() < _backoff_until:
        return 0  # Gupshup said slow down
    attempted = 0
    async with engine.connect() as conn:
        due = (await conn.execute(DUE_SQL)).mappings().all()
        if not due:
            return 0
        sent_24h = (await conn.execute(SENT_24H_SQL)).scalar() or 0
    budget = max(0, s.WA_DAILY_SEND_LIMIT - sent_24h)
    for camp in due:
        if budget <= 0:
            break
        n = min(_quota(camp["id"], camp["rate_per_minute"]), budget)
        ids = []
        if n:
            async with engine.connect() as conn:
                ids = [r[0] for r in await conn.execute(NEXT_QUEUED_SQL, {"cid": camp["id"], "n": n})]
        for rid in ids:
            attempted += 1
            if not await _send_one(engine, camp, rid):
                _backoff_until = time.monotonic() + BACKOFF_SECONDS
                return attempted
            budget -= 1
        async with engine.begin() as conn:
            await conn.execute(FINISH_SQL, {"cid": camp["id"]})
    return attempted


async def _send_one(engine, camp, rid) -> bool:
    """Send one recipient. False = Gupshup refused with 429/5xx: the row is back in the queue
    and the loop should back off."""
    async with engine.begin() as conn:
        await conn.execute(SKIP_OPTED_OUT_SQL, {"id": rid})
        row = (await conn.execute(CLAIM_SQL, {"id": rid})).mappings().first()
        if row is None:
            return True  # someone else claimed it, or it was just skipped as opted out / rejected
        owner = await wa_assign.assign_if_unassigned(conn, row["phone10"])
        await conn.execute(SET_OWNER_SQL, {"o": owner, "id": rid})
    variables = [str(v) for v in row["variables"]]
    res = await gupshup_template.send_template(row["phone10"], camp["gupshup_template_id"], variables)
    async with engine.begin() as conn:
        if res["ok"]:
            try:
                shown = render(camp["body"], variables)
            except (ValueError, IndexError):  # must never roll back the 'accepted' write: Gupshup already took it
                shown = f"[template {camp['template_name']}]"
            await conn.execute(ACCEPTED_SQL, {"g": res["message_id"], "id": rid})
            await conn.execute(WaMessage.__table__.insert().values(
                direction="out", phone="91" + row["phone10"], body=shown,
                msg_type="template", gupshup_id=res["message_id"], status="submitted",
                author=camp["created_by"], source_app="template",
                raw={"campaign_id": str(camp["id"]), "template": camp["template_name"]}))
        elif res.get("retry"):
            await conn.execute(REQUEUE_SQL, {"id": rid})
            return False
        elif not res.get("unknown"):
            await conn.execute(FAILED_SQL, {"e": res["error"][:500], "id": rid})
        # unknown: leave 'submitted' — Gupshup may have sent it; the admin retries by hand
    return True


_task: asyncio.Task | None = None


async def _loop() -> None:
    # ponytail: in-process, single RUN_SCHEDULER process (same as the dialer). Scaling to
    # >1 scheduler process would need a pg_try_advisory_lock around tick(); the claim
    # already stops a double send.
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the loop must survive anything
            log.exception("wa campaign sender: tick failed")
        await asyncio.sleep(TICK_SECONDS)


def start_campaign_sender() -> None:
    global _task
    if _task is None:
        _task = asyncio.create_task(_loop())
        log.info("wa campaign sender started (every %ds)", TICK_SECONDS)


def stop_campaign_sender() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None


TRANSITIONS = {  # action → (allowed from, to)
    "launch": ({"draft"}, "sending"),
    "pause": ({"sending"}, "paused"),
    "resume": ({"paused"}, "sending"),
    "cancel": ({"draft", "sending", "paused"}, "cancelled"),
}
LOGGED = {"launch": "launched", "pause": "paused", "resume": "resumed", "cancel": "cancelled"}  # spec §5.2 names


async def set_status(conn, cid, action: str, user: dict) -> str:
    allowed, to = TRANSITIONS[action]
    row = (await conn.execute(text("""
        UPDATE wa_campaigns SET status = :to,
               launched_at = CASE WHEN :to = 'sending' AND launched_at IS NULL THEN now() ELSE launched_at END
         WHERE id = :id AND status = ANY(:allowed)
        RETURNING (SELECT status FROM wa_campaigns WHERE id = :id) AS before"""),
        {"to": to, "id": cid, "allowed": list(allowed)})).first()
    if row is None:
        raise ValueError(f"can't {action} a campaign in that state")
    await activity.record(conn, activity.row_for(
        activity.Actor.of(user), entity_type="wa_campaign", entity_id=str(cid),
        action=f"wa_campaign_{LOGGED[action]}", field="status", before=row[0], after=to))
    return to


# ── Receipts from Gupshup callbacks (contract §3, Deltas 1, 2, 5, 11) ───────────────
STATUS_RANK = {"queued": 0, "submitted": 1, "accepted": 2, "sent": 3, "delivered": 4, "read": 5, "failed": 6}
# enqueued = 0: it only teaches the WhatsApp id ('accepted' already means Gupshup took it)
EVENT_RANK = {"enqueued": 0, "sent": 3, "delivered": 4, "read": 5, "failed": 6}

RECEIPT_SQL = text("""
    UPDATE wa_campaign_recipients
       SET status = CASE WHEN :rank > (CASE status WHEN 'queued' THEN 0 WHEN 'submitted' THEN 1
                                       WHEN 'accepted' THEN 2 WHEN 'sent' THEN 3 WHEN 'delivered' THEN 4
                                       WHEN 'read' THEN 5 WHEN 'failed' THEN 6 ELSE 7 END)
                         THEN CAST(:status AS text) ELSE status END,
           status_at = CASE WHEN :rank > (CASE status WHEN 'queued' THEN 0 WHEN 'submitted' THEN 1
                                          WHEN 'accepted' THEN 2 WHEN 'sent' THEN 3 WHEN 'delivered' THEN 4
                                          WHEN 'read' THEN 5 WHEN 'failed' THEN 6 ELSE 7 END)
                            THEN now() ELSE status_at END,
           error = COALESCE(CAST(:error AS text), error),
           whatsapp_id = COALESCE(whatsapp_id, CAST(:learn AS text))
     WHERE gupshup_id = :key OR whatsapp_id = CAST(:wa_id AS text)
    RETURNING campaign_id, phone10
""")
PAUSE_SQL = text("""
    UPDATE wa_campaigns SET status = 'paused', status_note = :note
     WHERE id = :cid AND status = 'sending'
""")


async def apply_receipt(conn, ev: dict) -> list[dict]:
    """A Gupshup message-event for a campaign message: forward-only status, keep the failure
    code, learn the WhatsApp id, and pause the campaign on a campaign-level failure."""
    typ = ev.get("type")
    if typ not in EVENT_RANK:
        return []
    ids = event_ids(ev)
    if not ids["key"] and not ids["wa_id"]:
        return []
    rows = [dict(r) for r in (await conn.execute(RECEIPT_SQL, {
        "rank": EVENT_RANK[typ], "status": typ, "error": event_error(ev), **ids})).mappings()]
    code = event_code(ev)
    if typ == "failed" and code in CAMPAIGN_STOP_CODES:
        for cid in {r["campaign_id"] for r in rows}:
            await conn.execute(PAUSE_SQL, {"cid": cid, "note": f"Paused by Gupshup error {event_error(ev)}"})
    return rows


# ── Campaign detail (spec §11) ──────────────────────────────────────────────────────
# ponytail: a tap with no context at all (not seen in Gupshup's docs, but cheap to cover) falls back to
# the time rule — the reply after this send and before the next send to the same number.
RECIPIENTS_SQL = text("""
    SELECT r.id, r.phone10, r.name, r.variables, r.status, r.skip_reason, r.error, r.owner,
           r.sent_at, r.status_at, rep.first_reply, rep.replied_at, rep.replies, btn.button
      FROM wa_campaign_recipients r
      LEFT JOIN LATERAL (
        SELECT (array_agg(m.body ORDER BY m.created_at))[1] AS first_reply,
               min(m.created_at)                             AS replied_at,
               count(*)                                      AS replies
          FROM wa_messages m
         WHERE right(m.phone, 10) = r.phone10 AND m.direction = 'in'
           AND r.sent_at IS NOT NULL AND m.created_at > r.sent_at
           AND NOT EXISTS (SELECT 1 FROM wa_campaign_recipients r2
                            WHERE r2.phone10 = r.phone10
                              AND r2.sent_at > r.sent_at AND r2.sent_at < m.created_at)
      ) rep ON true
      LEFT JOIN LATERAL (
        SELECT m.body AS button
          FROM wa_messages m
         WHERE m.direction = 'in' AND m.msg_type = 'quick_reply' AND right(m.phone, 10) = r.phone10
           AND (m.raw->'payload'->'context'->>'gsId' = r.gupshup_id
                OR m.raw->'payload'->'context'->>'id' = r.whatsapp_id
                OR (m.raw->'payload'->'context' IS NULL AND r.sent_at IS NOT NULL AND m.created_at > r.sent_at
                    AND NOT EXISTS (SELECT 1 FROM wa_campaign_recipients r3
                                     WHERE r3.phone10 = r.phone10
                                       AND r3.sent_at > r.sent_at AND r3.sent_at < m.created_at)))
         ORDER BY m.created_at
         LIMIT 1
      ) btn ON true
     WHERE r.campaign_id = :cid
       AND (CAST(:status AS text) IS NULL
            OR (:status = 'replied'  AND rep.replies > 0)
            OR (:status = 'no_reply' AND r.status IN ('accepted','sent','delivered','read') AND COALESCE(rep.replies, 0) = 0)
            OR (:status = 'sent'     AND r.status IN ('sent','delivered','read'))
            OR (:status = 'delivered' AND r.status IN ('delivered','read'))
            OR r.status = :status)
     ORDER BY rep.replied_at DESC NULLS LAST, r.sent_at DESC NULLS LAST
""")

NO_RETRY_CODES = {"131050": "they opted out of marketing messages — Meta says never retry",
                  "1002": "the number has no WhatsApp account"}


def retry_refusal(error: str | None, status_at) -> str | None:
    """Why a failed recipient must NOT be retried, or None (contract §8, Delta 18)."""
    from datetime import datetime, timedelta, timezone
    code = (error or "").split(":", 1)[0].strip()
    if code in NO_RETRY_CODES:
        return NO_RETRY_CODES[code]
    if code == "131049" and status_at and datetime.now(timezone.utc) - status_at < timedelta(hours=24):
        return "Meta's per-user marketing limit — wait 24 hours, an earlier retry can extend the block"
    return None


# ── Auto campaigns (spec §7) ──────────────────────────────────────────────────────
def next_slot_after(slot: date, every_days: int, *, today: date) -> date:
    """The slot after `slot`, skipping any that are already past — missed slots are not
    replayed (spec §7.3)."""
    nxt = slot + timedelta(days=every_days)
    while nxt <= today:
        nxt += timedelta(days=every_days)
    return nxt


# a definition is due once its slot's date + run_at has passed on the IST wall clock
DUE_AUTO_SQL = text("""
    SELECT a.*, t.active AS template_active
      FROM wa_auto_campaigns a JOIN wa_templates t ON t.id = a.template_id
     WHERE a.active AND t.active
       AND (a.next_slot + CAST(a.run_at AS time)) <= (now() AT TIME ZONE 'Asia/Kolkata')
""")
# "Run now" names its definition, so the time-of-day condition doesn't apply
ONE_AUTO_SQL = text("""
    SELECT a.*, t.active AS template_active
      FROM wa_auto_campaigns a JOIN wa_templates t ON t.id = a.template_id
     WHERE a.id = :id AND a.active AND t.active
""")
LAST_RUN_SQL = text("""
    SELECT id, status FROM wa_campaigns WHERE auto_campaign_id = :aid ORDER BY run_slot DESC LIMIT 1
""")
INSERT_RUN_SQL = text("""
    INSERT INTO wa_campaigns (id, name, template_id, source, repeat_of, auto_campaign_id, run_slot,
                              status, created_by, launched_at, send_window_start, send_window_end,
                              rate_per_minute)
    VALUES (:id, :name, :template_id, 'auto', :repeat_of, :aid, :slot, 'sending', 'cron', now(),
            :ws, :we, :rate)
    ON CONFLICT ON CONSTRAINT uq_wa_campaign_auto_slot DO NOTHING
    RETURNING id
""")
RUN_COUNT_SQL = text("SELECT count(*) FROM wa_campaigns WHERE auto_campaign_id = :aid")
TODAY_IST_SQL = text("SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date")
SET_NEXT_SLOT_SQL = text("UPDATE wa_auto_campaigns SET next_slot = :n WHERE id = :id")
FINISH_AUTO_SQL = text("UPDATE wa_auto_campaigns SET active = false, status_note = :note, updated_at = now() WHERE id = :id")
ADVANCE_AUTO_SQL = text("UPDATE wa_auto_campaigns SET next_slot = :n, status_note = NULL WHERE id = :id")


class _RepeatReq:
    """The attributes candidates_for() reads, for a repeat built by the cron."""
    def __init__(self, template_id, repeat_of, mode):
        self.template_id, self.source, self.repeat_of, self.repeat_mode = template_id, "repeat", repeat_of, mode
        self.var_cols, self.fixed, self.name_col, self.phone_col = [], [], None, 0


async def auto_list(conn, a, last) -> tuple:
    """(source campaign id, template row, classified rows) for an auto campaign's NEXT run.
    Shared by the cron run and the dry run so the two can never pick different people.
    Cooldown ignores the whole family — the seed and every earlier run of this auto
    campaign — because its own repeats are governed by every_days (spec §4.4)."""
    source = last["id"] if last else a["seed_campaign_id"]
    # the seed's whole repeat tree — every run sets repeat_of, so it holds the seed and all earlier runs
    family = [r[0] for r in await conn.execute(REPEAT_FAMILY_SQL, {"src": a["seed_campaign_id"]})]
    cands, t, _ = await candidates_for(conn, _RepeatReq(a["template_id"], source, a["repeat_mode"]))
    rows = await classify(conn, cands, cooldown_days=a["cooldown_days"], ignore_campaigns=family)
    return source, t, rows


async def auto_dry_run(conn, auto_id) -> dict:
    """Who the next run would message. Reads only — no campaign, no slot, no note is written."""
    a = (await conn.execute(select(WaAutoCampaign.__table__).where(WaAutoCampaign.id == auto_id))).mappings().first()
    if a is None:
        raise NotFound("auto campaign not found")
    last = (await conn.execute(LAST_RUN_SQL, {"aid": auto_id})).mappings().first()
    _, t, rows = await auto_list(conn, a, last)
    return {"counts": counts(rows), "samples": samples(t, rows)}


async def run_auto_campaigns(trigger: str = "cron", only=None) -> dict:
    """Turn every due slot into a campaign run. It only QUEUES — the web process's send loop sends.
    `only` = one definition's id, for "Run now" (its slot is due by definition, whatever the clock says)."""
    engine = neon_engine()
    if engine is None:
        return {"status": "not_configured", "runs": 0, "skipped": []}
    runs, skipped = 0, []
    async with engine.connect() as conn:
        due = (await conn.execute(ONE_AUTO_SQL, {"id": only}) if only else await conn.execute(DUE_AUTO_SQL)).mappings().all()
    for a in due:
        async with engine.begin() as conn:  # one transaction per definition: run + list + next_slot
            today = (await conn.execute(TODAY_IST_SQL)).scalar()
            slot = today if only else a["next_slot"]
            last = (await conn.execute(LAST_RUN_SQL, {"aid": a["id"]})).mappings().first()
            nxt = next_slot_after(slot, a["every_days"], today=today)
            if last and last["status"] in ("sending", "paused"):
                skipped.append({"auto": str(a["id"]), "reason": "previous run still sending"})
                await conn.execute(SET_NEXT_SLOT_SQL, {"n": nxt, "id": a["id"]})
                continue
            if a["max_runs"] and (await conn.execute(RUN_COUNT_SQL, {"aid": a["id"]})).scalar() >= a["max_runs"]:
                await conn.execute(FINISH_AUTO_SQL, {"id": a["id"], "note": "finished — max runs reached"})
                skipped.append({"auto": str(a["id"]), "reason": "max runs reached"})
                continue
            source, t, rows = await auto_list(conn, a, last)
            valid = [r for r in rows if r["status"] == "valid"]
            if not valid:
                await conn.execute(FINISH_AUTO_SQL, {"id": a["id"], "note": "finished — no one left to message"})
                skipped.append({"auto": str(a["id"]), "reason": "no one left to message"})
                continue
            rid = (await conn.execute(INSERT_RUN_SQL, {
                "id": uuid.uuid4(), "name": f"{a['name']} · {slot:%-d %b}", "template_id": a["template_id"],
                "repeat_of": source, "aid": a["id"], "slot": slot, "ws": a["send_window_start"],
                "we": a["send_window_end"], "rate": a["rate_per_minute"]})).first()
            if rid is not None:
                kept = [r for r in rows if r["status"] in ("valid", "skipped")]
                await conn.execute(WaCampaignRecipient.__table__.insert(), [{
                    "id": uuid.uuid4(), "campaign_id": rid[0], "phone10": r["phone10"], "name": r["name"],
                    "variables": r["variables"], "status": "queued" if r["status"] == "valid" else "skipped",
                    "skip_reason": r["reason"] if r["status"] == "skipped" else None,
                    "position": i} for i, r in enumerate(kept)])  # keep the seed list's order
                await activity.record(conn, activity.row_for(
                    None, entity_type="wa_auto", entity_id=str(a["id"]), action="wa_auto_run",
                    metadata={"campaign_id": str(rid[0]), "queued": len(valid), "slot": str(slot), "trigger": trigger}))
                runs += 1
            else:
                skipped.append({"auto": str(a["id"]), "reason": "this slot already ran"})
            await conn.execute(ADVANCE_AUTO_SQL, {"n": nxt, "id": a["id"]})
    log.info("auto campaigns (%s): %d run(s), %d skipped", trigger, runs, len(skipped))
    return {"status": "ok", "runs": runs, "skipped": skipped}
