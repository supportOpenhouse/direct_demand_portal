"""Fill / refresh sales_manager_list from Openhouse Core's crm/sales-managers/.

    cd backend
    uv run python scripts/22_fill_sales_managers.py            # dry run: fetch + count, write nothing
    uv run python scripts/22_fill_sales_managers.py --apply    # create the table if missing, upsert

Uses CRM_BOOKING_API_BASE_URL — PRODUCTION Core. Staging's manager ids are not prod's
(prod SMIDs 30/83/113/137/141 don't exist there), so never fill this from staging:
a stored id is what a visit gets reassigned to.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import dispose_engines, neon_engine  # noqa: E402
from app.services.sales_managers import refresh_sales_managers  # noqa: E402


async def main(apply: bool) -> None:
    s = get_settings()
    async with neon_engine().connect() as conn:
        db = (await conn.execute(text("SELECT current_database()"))).scalar()
    print(f"database: {db} @ {urlparse(s.DATABASE_URL).hostname}")
    print(f"core:     {urlparse(s.CRM_BOOKING_API_BASE_URL).hostname}")
    try:
        print(await refresh_sales_managers(apply=apply))
    finally:
        await dispose_engines()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    asyncio.run(main(ap.parse_args().apply))
