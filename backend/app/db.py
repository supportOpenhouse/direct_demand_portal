from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _engine_kwargs() -> dict:
    if settings.is_sqlite:
        # SQLite (local dev / tests): no server-side pool tuning.
        return {}
    # Neon Postgres: small pool against the direct (unpooled) endpoint.
    return dict(pool_size=5, max_overflow=5, pool_recycle=300, pool_pre_ping=True)


engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs())
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
