"""Fill app_visit_data from Openhouse Core's visits API — every crm_visits.visit_id,
100 per request.

    uv run python scripts/14_fill_app_visit_data.py

This writes to the live database — `backend/.env` points at production and there is no
staging — so it prints which database it is about to touch before it touches anything.

Creates the table first if it isn't there yet (a deploy's create_all would do the same;
the foreign key to crm_visits.visit_id comes with it). Safe to re-run: every run
refreshes each visit's row, and a visit Core now reports missing keeps its last copy.
"""
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import dispose_engines, neon_engine  # noqa: E402
from app.models import AppVisitData  # noqa: E402
from app.services.app_visit_data import run_app_visit_data_sync  # noqa: E402

SUMMARY = text("""
    SELECT count(*) AS rows,
           count(*) FILTER (WHERE found) AS found,
           count(*) FILTER (WHERE NOT found) AS missing,
           (SELECT count(*) FROM crm_visits) AS crm_visits
      FROM app_visit_data
""")


async def main() -> None:
    engine = neon_engine()
    if engine is None:
        sys.exit("DATABASE_URL not configured")
    host = urlparse(get_settings().DATABASE_URL).hostname
    try:
        async with engine.begin() as conn:
            db = (await conn.execute(text("SELECT current_database()"))).scalar()
            print(f"database: {db} @ {host}")
            await conn.run_sync(lambda c: AppVisitData.__table__.create(c, checkfirst=True))

        print(await run_app_visit_data_sync(trigger="script"))

        async with engine.connect() as conn:
            print(dict((await conn.execute(SUMMARY)).mappings().one()))
    finally:
        await dispose_engines()


if __name__ == "__main__":
    asyncio.run(main())
