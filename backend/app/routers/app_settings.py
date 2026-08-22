"""Org-wide settings: admin writes, everyone reads.

The read is deliberately NOT admin-only. An RM's browser has to know whether to hide
lead phone numbers, and it can only know that by asking — but only an admin may
decide it. That asymmetry is the whole endpoint.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from ..core.auth import current_user, require_admin
from ..db import neon_engine
from ..services import activity
from ..services.app_settings import DEFAULTS, LIST_KEYS, SETTING_KEYS, coerce, merge_defaults

log = logging.getLogger("app_settings")
router = APIRouter(prefix="/settings", tags=["settings"])

_UPSERT = text("""
    INSERT INTO app_settings (key, value, updated_at, updated_by)
    VALUES (:key, :value, now(), :by)
    ON CONFLICT (key) DO UPDATE
       SET value = EXCLUDED.value, updated_at = now(), updated_by = EXCLUDED.updated_by
""")


class SettingIn(BaseModel):
    # bool for flag settings, list[str] for list settings (e.g. an email allowlist)
    value: bool | list[str]


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
    # the value's type has to match the key's kind — a list into a flag (or vice versa)
    # is a client bug, not something to silently coerce away.
    if key in LIST_KEYS:
        if not isinstance(payload.value, list):
            raise HTTPException(status_code=400, detail=f"{key!r} expects a list")
        stored = json.dumps([str(x).strip().lower() for x in payload.value if str(x).strip()])
    else:
        if not isinstance(payload.value, bool):
            raise HTTPException(status_code=400, detail=f"{key!r} expects a boolean")
        stored = "true" if payload.value else "false"
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Set DATABASE_URL")
    async with engine.begin() as conn:
        await conn.execute(_UPSERT, {
            "key": key,
            # stored as text, coerced back on read — see services/app_settings.py
            "value": stored,
            "by": user.get("email"),
        })
        # hide_lead_phones is a PII policy switch — who flipped it and when is the
        # whole point of recording it.
        await activity.record(conn, activity.row_for(
            activity.Actor.of(user), entity_type="setting", entity_id=key,
            action="setting_changed", field=key, after=payload.value))
    log.info("setting %s = %s by %s", key, payload.value, user.get("email"))
    return {key: coerce(key, payload.value)}
