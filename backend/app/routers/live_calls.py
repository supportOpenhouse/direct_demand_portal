"""Live Calls — what the RM sees while a campaign is dialling them.

Deliberately separate from routers/dialer.py, which is admin-only because a campaign
rings other people's phones. Everything here is scoped to the caller and returns only
their own rows, so it runs on `current_user`.

The auto-dialer rings the RM's handset first and bridges the lead second, so without
this page the RM answers a call with no idea who is on the other end. It shows three
things: who they are on with now, who is queued, and what they have already called
today with whether they have marked the result.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from ..core.auth import current_user
from ..db import neon_engine
from ..events import rm_channel, subscribe
from ..services.dialer import _in_window

log = logging.getLogger("live_calls")
router = APIRouter(prefix="/dialer", tags=["dialer"])

# Every running campaign this RM is in. `rms` is a JSONB array of emails; lower() on
# both sides because the pool is hand-entered and the JWT's casing is Google's.
_MY_CAMPAIGNS = text("""
    SELECT id, name, strategy, window_start, window_end
      FROM dial_campaigns
     WHERE status = 'running'
       AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(rms) e
                    WHERE lower(e) = lower(:email))
     ORDER BY created_at DESC
""")

# The lead whose phone is ringing on this RM's handset right now. Everything the RM
# needs to open the call with: who they are, what they asked for, and whether we have
# spoken to them before.
_NOW_CALLING = text("""
    SELECT q.id, q.lead_id, q.dialed_at, q.attempts,
           l.name, l.phone, l.society, l.city, l.configuration,
           l.budget_band AS budget,
           l.stage, l.miss_count, l.ever_connected
      FROM dial_queue q
      JOIN leads l ON l.id = q.lead_id
     WHERE q.campaign_id = :cid
       AND q.status = 'dialing'
       AND lower(q.rm_email) = lower(:email)
     ORDER BY q.dialed_at DESC
     LIMIT 1
""")

# Today's calls, newest first. `call_result` NULL is what renders the "needs result"
# badge, so it has to come back even though nothing else reads it.
#
# The day boundary is IST on both sides: calling windows are IST wall-clock, so the
# RM's "today" is the IST day. Comparing on UTC would clear this list at 05:30 IST,
# mid-shift for an early campaign, and take unmarked calls out of reach with it.
#
# Not scoped to a campaign: a campaign that finished at 18:00 still leaves unmarked
# calls the RM should be able to reach at 18:30.
_COMPLETED_TODAY = text("""
    SELECT q.id, q.lead_id, q.dialed_at, q.ended_at, q.answered, q.outcome,
           q.attempts, q.call_result, q.call_result_at,
           l.name, l.phone, l.society, l.city, l.stage
      FROM dial_queue q
      JOIN leads l ON l.id = q.lead_id
     WHERE lower(q.rm_email) = lower(:email)
       AND q.dialed_at IS NOT NULL
       AND (q.dialed_at AT TIME ZONE 'Asia/Kolkata')::date
         = (now()        AT TIME ZONE 'Asia/Kolkata')::date
     ORDER BY q.dialed_at DESC
     LIMIT 100
""")

_UPCOMING = """
    SELECT q.id, q.lead_id, q.position,
           l.name, l.society, l.city, l.configuration,
           l.budget_band AS budget, l.stage
      FROM dial_queue q
      JOIN leads l ON l.id = q.lead_id
     WHERE q.campaign_id = :cid
       AND q.status = 'pending'
       {mine}
     ORDER BY q.position, q.id
     LIMIT 25
"""


def upcoming_sql(strategy: str):
    """The queue ahead of this RM.

    Only the 'assigned' strategy stamps rm_email up front (assign_owners does it when
    the campaign starts). Under round_robin and least_load the column stays NULL until
    _dial_next claims the row, so filtering on it there returns nothing at all — the
    honest answer is the shared pool, which the UI labels as such.
    """
    mine = "AND lower(q.rm_email) = lower(:email)" if strategy == "assigned" else ""
    return text(_UPCOMING.format(mine=mine))


def live_campaign(rows, in_window=_in_window):
    """The campaign actually dialling this RM right now, or None.

    _assert_no_rm_conflict only refuses campaigns whose calling windows OVERLAP, so an
    RM can legitimately sit in two running campaigns at different hours. The one whose
    window is open is the one ringing their phone.
    """
    for row in rows:
        if in_window(row["window_start"], row["window_end"]):
            return row
    return None


# Render closes idle connections. A comment keeps the socket warm without the client
# having to parse a periodic empty event.
SSE_KEEPALIVE = ": keepalive\n\n"
_KEEPALIVE_SECONDS = 25


def sse_frame(event: dict) -> str:
    """One SSE event. json.dumps is what keeps a newline inside a lead name or a dial
    failure detail from terminating the frame early."""
    return f"data: {json.dumps(event, default=str)}\n\n"


def _shape_lead(row: dict) -> dict:
    out = {k: v for k, v in dict(row).items()}
    out["id"] = str(out["id"])
    if out.get("lead_id") is not None:
        out["lead_id"] = str(out["lead_id"])
    return out


@router.get("/my-calls")
async def my_calls(user: dict = Depends(current_user)):
    """Snapshot for the Live Calls page.

    Doubles as the polling fallback: when the SSE stream can't run — no Redis across a
    split scheduler process, a dropped connection — the page polls this instead, and
    degrades to a few seconds of latency rather than to nothing.
    """
    email = user.get("email") or ""
    engine = neon_engine()
    if engine is None:
        # Must carry every key the real answer does — a missing upcoming_is_shared
        # reads as undefined on the page, and a shared pool would then render as if
        # those leads were this RM's own.
        return {"campaign": None, "upcoming_is_shared": False,
                "now_calling": None, "upcoming": [], "completed": []}

    async with engine.connect() as conn:
        running = (await conn.execute(_MY_CAMPAIGNS, {"email": email})).mappings().all()
        campaign = live_campaign([dict(r) for r in running])

        now_calling, upcoming = None, []
        if campaign is not None:
            args = {"cid": campaign["id"], "email": email}
            row = (await conn.execute(_NOW_CALLING, args)).mappings().first()
            now_calling = _shape_lead(row) if row else None
            upcoming = [_shape_lead(r) for r in (
                await conn.execute(upcoming_sql(campaign["strategy"]), args)).mappings().all()]

        completed = [_shape_lead(r) for r in (
            await conn.execute(_COMPLETED_TODAY, {"email": email})).mappings().all()]

    return {
        "campaign": None if campaign is None else {
            "id": str(campaign["id"]), "name": campaign["name"],
            "strategy": campaign["strategy"],
            "window_start": campaign["window_start"], "window_end": campaign["window_end"],
        },
        # under round_robin/least_load the queue is a shared pool — the next lead in it
        # may well ring somebody else's phone, and the UI has to say so
        "upcoming_is_shared": campaign is not None and campaign["strategy"] != "assigned",
        "now_calling": now_calling,
        "upcoming": upcoming,
        "completed": completed,
    }


@router.get("/my-calls/stream")
async def my_calls_stream(request: Request, user: dict = Depends(current_user)):
    """Push notification that this RM's call state moved.

    Carries only a nudge — {"type", "queue_item_id"} — and the page refetches
    /my-calls. One authoritative query builds the payload; the stream never rebuilds
    it, so the two can't drift.

    Consumed with fetch() + ReadableStream rather than EventSource: auth is a Bearer
    header (api.ts) and EventSource can't set headers. The usual `?token=` workaround
    would put the JWT in access logs and referrers.
    """
    channel = rm_channel(user.get("email") or "")

    async def stream():
        # Flushes headers immediately so the client's "connected" state is honest
        # rather than pending until the first call happens.
        yield SSE_KEEPALIVE
        events = subscribe(channel)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        events.__anext__(), timeout=_KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield SSE_KEEPALIVE
                    continue
                except StopAsyncIteration:
                    break  # Redis path gave up; the client falls back to polling
                yield sse_frame(event)
        finally:
            await events.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # stops any proxy from buffering the stream
    })
