"""Fill / refresh onboarded_properties.app_listed_videos (Openhouse STUDIO DB) from
Openhouse Core's get-homes-video/ — the video each home has listed in the Openhouse app.

    cd backend
    uv run python scripts/23_fill_app_listed_videos.py            # dry run: fetch + count, write nothing
    uv run python scripts/23_fill_app_listed_videos.py --apply    # add the column if missing, write

Core: `{CRM_BOOKING_API_BASE_URL}get-homes-video/` with header X-OpenHouse-Studio-Key
(OPENHOUSE_STUDIO_API_KEY). PRODUCTION Core only — staging's home ids are not prod's, so a
staging fill would put videos on the wrong homes. Answer (5 Oct): {"homeVideo": [{homeId,
societyName, video}]}, ONE video URL per home — so the column is TEXT despite its name.

Matched on onboarded_properties.core_home_id = homeId. A full refresh: every listed home is
set, and a home Core no longer lists goes back to NULL. An EMPTY answer is refused rather
than applied — it would clear every row.

⚠️ The Studio app owns this table and manages it with Alembic. This column is not in its
models, so its next `alembic revision --autogenerate` will propose DROPPING it — whoever
runs their migrations needs to know, or add the column to their model.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import dispose_engines, studio_engine  # noqa: E402

COLUMN_EXISTS = text("""
    SELECT 1 FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = 'onboarded_properties'
       AND column_name = 'app_listed_videos'
""")
ADD_COLUMN = text("ALTER TABLE onboarded_properties ADD COLUMN IF NOT EXISTS app_listed_videos TEXT")

# one statement, real rowcount: unnest of two parallel arrays (executemany's count is meaningless)
SET_LISTED = text("""
    UPDATE onboarded_properties p SET app_listed_videos = v.url
      FROM unnest(CAST(:homes AS int[]), CAST(:urls AS text[])) AS v(home, url)
     WHERE p.core_home_id = v.home AND p.app_listed_videos IS DISTINCT FROM v.url
""")
CLEAR_UNLISTED = text("""
    UPDATE onboarded_properties SET app_listed_videos = NULL
     WHERE app_listed_videos IS NOT NULL
       AND (core_home_id IS NULL OR core_home_id <> ALL(CAST(:homes AS int[])))
""")
MATCHED = text("SELECT count(*) FROM onboarded_properties WHERE core_home_id = ANY(CAST(:homes AS int[]))")


def fetch_listed() -> dict[int, str]:
    """{homeId: video URL} from Core. Raises on anything but a well-formed answer."""
    s = get_settings()
    if not (s.CRM_BOOKING_API_BASE_URL and s.OPENHOUSE_STUDIO_API_KEY):
        sys.exit("set CRM_BOOKING_API_BASE_URL and OPENHOUSE_STUDIO_API_KEY")
    url = s.CRM_BOOKING_API_BASE_URL.rstrip("/") + "/get-homes-video/"
    r = httpx.get(url, headers={"X-OpenHouse-Studio-Key": s.OPENHOUSE_STUDIO_API_KEY}, timeout=120)
    r.raise_for_status()
    listed: dict[int, str] = {}
    for e in r.json()["homeVideo"]:
        video = e["video"]
        if not (isinstance(video, str) and video.startswith("https://")):
            raise ValueError(f"home {e['homeId']}: not a video URL: {video!r}")
        listed[int(e["homeId"])] = video
    if not listed:
        raise ValueError("Core listed no videos at all — refusing to clear every row")
    return listed


async def main(apply: bool) -> None:
    s = get_settings()
    engine = studio_engine()
    if engine is None:
        sys.exit("set OPENHOUSE_STUDIO_DATABASE_URL")
    print(f"core:   {urlparse(s.CRM_BOOKING_API_BASE_URL).hostname}")
    listed = fetch_listed()
    homes, urls = list(listed), list(listed.values())
    try:
        async with engine.begin() as conn:
            db = (await conn.execute(text("SELECT current_database()"))).scalar()
            print(f"studio: {db} @ {urlparse(s.OPENHOUSE_STUDIO_DATABASE_URL).hostname}")
            matched = (await conn.execute(MATCHED, {"homes": homes})).scalar()
            print(f"Core lists {len(listed)} homes; {matched} onboarded properties carry one of those home ids")
            if not apply:
                has_col = (await conn.execute(COLUMN_EXISTS)).first() is not None
                print(f"column app_listed_videos: {'exists' if has_col else 'MISSING — --apply adds it'}")
                print("dry run — nothing written. Re-run with --apply.")
                return
            await conn.execute(ADD_COLUMN)
            set_n = (await conn.execute(SET_LISTED, {"homes": homes, "urls": urls})).rowcount
            clear_n = (await conn.execute(CLEAR_UNLISTED, {"homes": homes})).rowcount
            print(f"applied: {set_n} rows set/changed, {clear_n} rows cleared (no longer listed)")
    finally:
        await dispose_engines()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    asyncio.run(main(ap.parse_args().apply))
