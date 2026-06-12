"""Two lazy async engines: Neon (app DB) and the external properties DB (read-only).

Engines are created on first use, never at import — the app must boot with an
empty .env and simply report "not_configured".
"""
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import get_settings

_neon_engine: AsyncEngine | None = None
_properties_engine: AsyncEngine | None = None


def neon_engine() -> AsyncEngine | None:
    global _neon_engine
    settings = get_settings()
    if not settings.neon_configured:
        return None
    if _neon_engine is None:
        _neon_engine = create_async_engine(
            settings.neon_url,
            pool_size=5,
            max_overflow=5,
            pool_recycle=300,
            pool_pre_ping=True,
        )
    return _neon_engine


def properties_engine() -> AsyncEngine | None:
    global _properties_engine
    settings = get_settings()
    if not settings.properties_configured:
        return None
    if _properties_engine is None:
        # Someone else's production DB: tiny pool, read-only queries only.
        _properties_engine = create_async_engine(
            settings.properties_url,
            pool_size=2,
            max_overflow=2,
            pool_recycle=300,
            pool_pre_ping=True,
        )
    return _properties_engine


async def dispose_engines() -> None:
    global _neon_engine, _properties_engine
    if _neon_engine is not None:
        await _neon_engine.dispose()
        _neon_engine = None
    if _properties_engine is not None:
        await _properties_engine.dispose()
        _properties_engine = None
