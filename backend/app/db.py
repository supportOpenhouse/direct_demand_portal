"""Lazy async engines: Neon (app DB) plus the external read-only ones (properties,
direct inventory, Openhouse Studio).

Engines are created on first use, never at import — the app must boot with an
empty .env and simply report "not_configured".
"""
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import get_settings

_neon_engine: AsyncEngine | None = None
_properties_engine: AsyncEngine | None = None
_direct_inventory_engine: AsyncEngine | None = None
_studio_engine: AsyncEngine | None = None


def neon_engine() -> AsyncEngine | None:
    global _neon_engine
    settings = get_settings()
    if not settings.neon_configured:
        return None
    if _neon_engine is None:
        # Neon sits a long round trip away, so re-establishing a connection (TLS +
        # auth) costs ~1s and shows up directly in request latency. Recycling every
        # 5 min meant normal bursty use kept paying that; pre_ping already discards
        # anything the server dropped, so a long recycle is the safe way to stay warm.
        _neon_engine = create_async_engine(
            settings.neon_url,
            pool_size=5,
            max_overflow=5,
            pool_recycle=1800,
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


def direct_inventory_engine() -> AsyncEngine | None:
    global _direct_inventory_engine
    settings = get_settings()
    if not settings.direct_inventory_configured:
        return None
    if _direct_inventory_engine is None:
        # read-only reference prices (oh_pricing); small pool
        _direct_inventory_engine = create_async_engine(
            settings.direct_inventory_url,
            pool_size=2,
            max_overflow=2,
            pool_recycle=300,
            pool_pre_ping=True,
        )
    return _direct_inventory_engine


def studio_engine() -> AsyncEngine | None:
    global _studio_engine
    settings = get_settings()
    if not settings.studio_configured:
        return None
    if _studio_engine is None:
        # Openhouse Studio's DB (shoot videos + photos): someone else's, read-only, tiny pool
        _studio_engine = create_async_engine(
            settings.studio_url,
            pool_size=2,
            max_overflow=2,
            pool_recycle=300,
            pool_pre_ping=True,
        )
    return _studio_engine


async def dispose_engines() -> None:
    global _neon_engine, _properties_engine, _direct_inventory_engine, _studio_engine
    if _neon_engine is not None:
        await _neon_engine.dispose()
        _neon_engine = None
    if _properties_engine is not None:
        await _properties_engine.dispose()
        _properties_engine = None
    if _direct_inventory_engine is not None:
        await _direct_inventory_engine.dispose()
        _direct_inventory_engine = None
    if _studio_engine is not None:
        await _studio_engine.dispose()
        _studio_engine = None
