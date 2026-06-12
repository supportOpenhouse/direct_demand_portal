from fastapi import APIRouter
from sqlalchemy import text

from ..config import get_settings
from ..db import neon_engine, properties_engine

router = APIRouter(tags=["health"])


async def _ping(engine) -> str:
    if engine is None:
        return "not_configured"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


@router.get("/health")
async def health():
    settings = get_settings()
    return {
        "neon": await _ping(neon_engine()),
        "properties": await _ping(properties_engine()),
        "sheets": "ok" if settings.sheets_configured else "not_configured",
        "version": "phase-1",
    }
