from fastapi import APIRouter, Response
from sqlalchemy import text

from ..cache import redis_ping
from ..config import get_settings
from ..db import direct_inventory_engine, neon_engine, properties_engine

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


@router.get("/health/live")
async def health_live():
    """Liveness — cheap, no I/O. K8s/Render restart the container if this fails, so it
    must NOT depend on the DB (a DB blip should deroute traffic, not kill the pod)."""
    return {"status": "ok"}


@router.get("/health")
async def health(response: Response):
    """Readiness — gated on the primary DB (Neon). Returns 503 when Neon is down so
    the platform stops routing traffic here. Properties/sheets/redis are informational
    (external/optional, so they don't fail readiness)."""
    settings = get_settings()
    neon = await _ping(neon_engine())
    # only fail readiness when Neon is *configured but broken*, not when unconfigured (dev)
    if neon == "error":
        response.status_code = 503
    return {
        "neon": neon,
        "properties": await _ping(properties_engine()),
        "direct_inventory": await _ping(direct_inventory_engine()),
        "sheets": "ok" if settings.sheets_configured else "not_configured",
        "redis": await redis_ping(),
        "version": "1.0",
    }
