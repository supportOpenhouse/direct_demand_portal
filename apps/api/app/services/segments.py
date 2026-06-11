"""Segment criteria (HANDOVER §6.3) — purely date-driven, computed in Python.

NEVER use func.now()/SQL intervals here: cutoffs are Python datetimes passed as
bind params so SQLite (naive UTC strings) and Postgres (timestamptz) agree.
"""
from datetime import datetime, timedelta

from app.core.errors import ApiError
from app.models import Lead

TERMINAL_STAGES = ("won", "lost", "future_prospect", "timepass")
QUALIFIED_WINDOW_DAYS = 7


def segment_criteria(segment: str, now: datetime) -> list:
    cutoff = now - timedelta(days=QUALIFIED_WINDOW_DAYS)
    if segment == "new":
        return [Lead.confirmed.is_(False), Lead.stage.notin_(TERMINAL_STAGES)]
    if segment == "qualified":
        return [
            Lead.confirmed.is_(True),
            Lead.stage.notin_(TERMINAL_STAGES),
            Lead.qualified_at > cutoff,
        ]
    if segment == "pipeline":
        return [
            Lead.confirmed.is_(True),
            Lead.stage.notin_(TERMINAL_STAGES),
            Lead.qualified_at <= cutoff,
        ]
    if segment == "converted":
        return [Lead.stage == "won"]
    raise ApiError(422, "Validation error", {"segment": "must be one of new|qualified|pipeline|converted"})
