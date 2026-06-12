"""Local-dev bootstrap: `python -m app.devdb`

SQLite DATABASE_URL -> create_all + idempotent seed. For Postgres, use:
    uv run alembic upgrade head && uv run python -m app.seed
"""
import asyncio

from app.config import settings


async def main() -> None:
    if not settings.is_sqlite:
        print(
            "DATABASE_URL is not SQLite. For Postgres run:\n"
            "  uv run alembic upgrade head\n"
            "  uv run python -m app.seed"
        )
        return

    from app.db import SessionLocal, engine
    from app.models import Base
    from app.seed import seed

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        summary = await seed(session)
    await engine.dispose()
    print(f"Dev DB ready at {settings.DATABASE_URL}")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
