"""Openhouse Studio's stitched walkthrough video, for OTHER apps — server-to-server.

    GET /v1/external/studio-video/{core_home_id},{core_home_id},...
    X-CRM-Key: <CRM_API_KEY>

One entry per requested id, in the order asked, each with its own `status` — "ok",
"not_stitched" (home known, no video of either kind yet) or "not_found" (no property has
that id). A batch can't answer 404 for one id among many, so it is always 200 once the
key and the id list are valid.

The video is the stitched walkthrough, else the one the home has listed in the Openhouse
app (`onboarded_properties.app_listed_videos`, filled by scripts/23). It is returned in
`stitched_url` either way — that field name was already shared — and `source` says which
("stitched" | "app_listed"); `stitched_at` is set only for a stitched one.

Not the portal UI: no JWT, the caller holds our CRM_API_KEY (the same key, and the same
header, Openhouse Core already uses with us). Read-only, one query per request.

The video lives in the Openhouse Studio DB: `onboarded_properties.core_home_id` →
`uid` → `onboarded_properties_videos.stitched_url` (property_uid). On 5 Oct, 109 homes
with a core_home_id had a stitched video.
"""
import secrets

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import text

from ..config import get_settings
from ..db import studio_engine

router = APIRouter(tags=["external"])

# A whole property book in one call (~400 today), and a ceiling so one request can't ask
# for an unbounded ANY() list.
MAX_IDS = 500

# LEFT JOIN so "no such home" and "home known, no video yet" are two different answers.
# A home id can sit on two properties (12 does: the same Camellias unit onboarded twice,
# both stitched) — DISTINCT ON keeps one per home: a stitched one first, then one with an
# app-listed video, then the most recently stitched, then uid for a stable pick.
VIDEOS_BY_HOME = text("""
    SELECT DISTINCT ON (p.core_home_id) p.core_home_id, p.uid,
           nullif(v.stitched_url, '') AS stitched_url, v.stitched_at, p.app_listed_videos
      FROM onboarded_properties p
      LEFT JOIN onboarded_properties_videos v ON v.property_uid = p.uid
     WHERE p.core_home_id = ANY(:homes)
     ORDER BY p.core_home_id, (nullif(v.stitched_url, '') IS NOT NULL) DESC,
              (p.app_listed_videos IS NOT NULL) DESC, v.stitched_at DESC NULLS LAST, p.uid
""")


def _parse_ids(raw: str) -> list[int]:
    """"12, 630,12" → [12, 630]: integers only, de-duplicated, request order kept."""
    try:
        ids = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="core_home_ids must be comma-separated integers") from None
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise HTTPException(status_code=422, detail="give at least one core_home_id")
    if len(ids) > MAX_IDS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_IDS} core_home_ids per request")
    return ids


def _check_key(key: str | None) -> None:
    """Fail closed: an unset key refuses every caller (in dev too) rather than opening
    prod's studio data to anyone. Constant-time compare — a plain == leaks the key one
    character at a time to anyone timing the response."""
    secret = (get_settings().CRM_API_KEY or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="not configured — set CRM_API_KEY")
    if not secrets.compare_digest(key or "", secret):
        raise HTTPException(status_code=401, detail="Authentication required.")


@router.get("/external/studio-video/{core_home_ids}")
async def studio_videos(core_home_ids: str,
                        x_crm_key: str | None = Header(default=None, alias="X-CRM-Key")):
    _check_key(x_crm_key)
    ids = _parse_ids(core_home_ids)
    engine = studio_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="not configured — set OPENHOUSE_STUDIO_DATABASE_URL")
    async with engine.connect() as conn:
        found = {r["core_home_id"]: r for r in
                 (await conn.execute(VIDEOS_BY_HOME, {"homes": ids})).mappings()}
    items = []
    for home in ids:
        r = found.get(home)
        stitched = r["stitched_url"] if r else None
        url = stitched or (r["app_listed_videos"] if r else None)
        items.append({
            "core_home_id": home,
            "status": "ok" if url else "not_stitched" if r else "not_found",
            "uid": r["uid"] if r else None,
            "stitched_url": url,
            "source": "stitched" if stitched else "app_listed" if url else None,
            "stitched_at": r["stitched_at"].isoformat() if stitched and r["stitched_at"] else None,
        })
    return {"items": items}
