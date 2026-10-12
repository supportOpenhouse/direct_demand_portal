"""The search box's Claude mode — `POST /v1/lead-search/claude`. Admins only for now.

Scoped like the list it filters: `_role_scope` (the same clause the lead lists use) AND
the page's segment predicate, so Claude reads exactly the leads that page could show.
Home → Table sends no segment and searches the whole book.

EVERY search is written to activity_log (`claude_search`) — the query, how many leads were
read and matched, Claude's note, and any error — whether it succeeded or not. The note and
errors are also what the page shows in its popup.
"""
import logging
import time

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..core.auth import require_admin
from ..db import neon_engine
from ..services import activity
from ..services.claude_search import MAX_QUERY, load_book, search
from .leads import SEGMENTS, _role_scope

log = logging.getLogger("claude_search")

router = APIRouter(tags=["lead-search"])


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=MAX_QUERY)
    segment: str | None = None  # a SEGMENTS key; None = every stage


async def _log(user: dict, meta: dict) -> None:
    """Its own short transaction: there's no business write to ride along with, and a
    search that FAILED must be logged too. activity.record never raises."""
    async with neon_engine().begin() as conn:
        await activity.record(conn, activity.row_for(
            activity.Actor.of(user), entity_type="lead_search", entity_id=None,
            action="claude_search", metadata=meta))


@router.post("/lead-search/claude")
async def claude_search(payload: SearchIn, user: dict = Depends(require_admin)):
    if not get_settings().CLAUDE_API_KEY:
        raise HTTPException(status_code=503, detail="Claude search isn't configured — set CLAUDE_API_KEY")
    if payload.segment is not None and payload.segment not in SEGMENTS:
        raise HTTPException(status_code=400, detail=f"unknown segment '{payload.segment}'")
    if neon_engine() is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    query = payload.query.strip()
    scope, params = _role_scope(user)
    if payload.segment:
        scope = f"({SEGMENTS[payload.segment]}) AND ({scope})"
    meta: dict = {"query": query, "segment": payload.segment}
    started = time.monotonic()
    try:
        async with neon_engine().connect() as conn:
            book = await load_book(conn, scope, params)
        if not book:
            out = {"lead_ids": [], "note": "There are no leads here to search.", "leads_read": 0,
                   "parts": 0, "usage": None}
        else:
            out = await search(query, book)
        meta |= {"matched": len(out["lead_ids"]), "leads_read": out["leads_read"],
                 "parts": out["parts"], "note": out["note"] or None, "usage": out["usage"]}
        return {k: out[k] for k in ("lead_ids", "note", "leads_read")}
    except ValueError as e:  # refusal / too many matches — said in plain words by search()
        meta["error"] = str(e)
        raise HTTPException(status_code=422, detail=str(e)) from None
    except anthropic.RateLimitError:
        meta["error"] = "rate limited"
        raise HTTPException(status_code=429, detail="Claude is busy (rate limit) — try again in a minute.") from None
    except anthropic.APIStatusError as e:
        meta["error"] = f"Claude API {e.status_code}: {e.message}"
        raise HTTPException(status_code=502, detail=meta["error"]) from None
    except anthropic.APIConnectionError:
        meta["error"] = "couldn't reach Claude"
        raise HTTPException(status_code=502, detail="Couldn't reach Claude — try again.") from None
    finally:
        meta["seconds"] = round(time.monotonic() - started, 1)
        log.info("claude_search by=%s %s", user.get("email"), {k: meta.get(k) for k in ("matched", "leads_read", "error")})
        await _log(user, meta)
