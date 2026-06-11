"""TAT (HANDOVER §6.2): deadline set at ingest, cleared on first confirm;
ok / warn / breach derived at read time."""
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.utils import ensure_utc
from app.models import SettingsIntegration


def compute_tat(lead, now: datetime) -> dict:
    """-> {state: ok|warn|breach|None, deadline: datetime|None, minutes_left: int|None}"""
    if lead.confirmed or lead.tat_deadline is None:
        return {"state": None, "deadline": None, "minutes_left": None}
    deadline = ensure_utc(lead.tat_deadline)
    minutes_left = int((deadline - now).total_seconds() // 60)
    if now > deadline:
        state = "breach"
    elif minutes_left <= settings.TAT_WARN_WINDOW_MINUTES:
        state = "warn"
    else:
        state = "ok"
    return {"state": state, "deadline": deadline, "minutes_left": minutes_left}


async def tat_minutes_for_source(session: AsyncSession, source: str) -> int:
    """Per-source override from settings_integrations key 'tat_config':
    value = {"default": 60, "per_source": {"meta": 30, ...}}"""
    row = await session.get(SettingsIntegration, "tat_config")
    if row is not None and isinstance(row.value, dict):
        per_source = row.value.get("per_source") or {}
        if source in per_source:
            return int(per_source[source])
        if "default" in row.value:
            return int(row.value["default"])
    return settings.TAT_DEFAULT_MINUTES


def tat_deadline_for(created_at: datetime, minutes: int) -> datetime:
    return ensure_utc(created_at) + timedelta(minutes=minutes)
