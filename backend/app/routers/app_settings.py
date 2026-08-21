"""Org-wide settings: admin writes, everyone reads.

The read is deliberately NOT admin-only. An RM's browser has to know whether to hide
lead phone numbers, and it can only know that by asking — but only an admin may
decide it. That asymmetry is the whole endpoint.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from ..core.auth import current_user, require_admin
from ..db import neon_engine
from ..services import activity
from ..services.app_settings import DEFAULTS, SETTING_KEYS, coerce, merge_defaults

log = logging.getLogger("app_settings")
router = APIRouter(prefix="/settings", tags=["settings"])

_UPSERT = text("""
    INSERT INTO app_settings (key, value, updated_at, updated_by)
    VALUES (:key, :value, now(), :by)
    ON CONFLICT (key) DO UPDATE
       SET value = EXCLUDED.value, updated_at = now(), updated_by = EXCLUDED.updated_by
""")


class SettingIn(BaseModel):
    value: bool


@router.get("")
async def get_settings_values(_: dict = Depends(current_user)):
    """Every known setting, defaults filled in. Never fails: a settings read that 500s
    would take down every page that gates on one."""
    engine = neon_engine()
    if engine is None:
        return DEFAULTS
    try:
        async with engine.connect() as conn:
            stored = dict((await conn.execute(
                text("SELECT key, value FROM app_settings"))).all())
    except Exception:  # noqa: BLE001 — a missing table must not break the app
        log.exception("settings read failed — serving defaults")
        return DEFAULTS
    return merge_defaults(stored)


# PATCH, not PUT: CORS allow_methods in main.py doesn't list PUT, so a PUT would be
# blocked in the browser before it ever reached here. PATCH is also what users.py uses.
@router.patch("/{key}")
async def set_setting(key: str, payload: SettingIn, user: dict = Depends(require_admin)):
    if key not in SETTING_KEYS:
        raise HTTPException(status_code=400, detail=f"unknown setting {key!r}")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        await conn.execute(_UPSERT, {
            "key": key,
            # stored as text, coerced back on read — see services/app_settings.py
            "value": "true" if payload.value else "false",
            "by": user.get("email"),
        })
        # hide_lead_phones is a PII policy switch — who flipped it and when is the
        # whole point of recording it.
        await activity.record(conn, activity.row_for(
            activity.Actor.of(user), entity_type="setting", entity_id=key,
            action="setting_changed", field=key, after=payload.value))
    log.info("setting %s = %s by %s", key, payload.value, user.get("email"))
    return {key: coerce(key, payload.value)}
