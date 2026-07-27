"""Google OAuth verification + app JWT.

Graceful: when GOOGLE_OAUTH_CLIENT_ID is unset, `current_user` returns a synthetic
admin so the API stays open (the live deployment never locks out until auth is
deliberately configured on both sides)."""
import logging
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import get_settings

log = logging.getLogger("auth")
_bearer = HTTPBearer(auto_error=False)

OPEN_USER = {"id": "open", "email": "open@local", "name": "Open Access", "role": "admin", "picture": None}


def verify_google_token(credential: str) -> dict:
    """Verify a Google ID token (the credential from Google Identity Services).
    Returns {sub, email, name, picture}. Raises HTTPException(401) on failure."""
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token

    settings = get_settings()
    try:
        info = id_token.verify_oauth2_token(
            credential, g_requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"invalid Google token: {e}")
    if not info.get("email_verified"):
        raise HTTPException(status_code=401, detail="email not verified")
    domain = settings.ALLOWED_EMAIL_DOMAIN.strip()
    if domain and not (info.get("email", "").endswith("@" + domain)):
        raise HTTPException(status_code=403, detail=f"only @{domain} accounts are allowed")
    return {
        "sub": info["sub"], "email": info["email"],
        "name": info.get("name"), "picture": info.get("picture"),
    }


def issue_jwt(user: dict) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]), "email": user["email"], "role": user["role"],
        "name": user.get("name"), "picture": user.get("picture"),
        "assignment_name": user.get("assignment_name"),
        "iat": now, "exp": now + timedelta(hours=settings.JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


# --- "force logout everyone" cutoff -----------------------------------------
# A token is honoured only if it was issued at/after this timestamp; bumping the
# cutoff to now() invalidates every live session at once. Stored in sync_state
# (durable) and cached in-process (short TTL) so auth doesn't hit the DB on every
# request. Multi-instance: other workers pick up the new cutoff within the TTL.
_AUTH_EPOCH_KEY = "auth:sessions_valid_from"
_EPOCH_TTL = 30.0
_epoch_cache: dict = {"value": None, "read_at": 0.0}  # value = unix seconds | None


async def _read_auth_epoch() -> float | None:
    if time.monotonic() - _epoch_cache["read_at"] < _EPOCH_TTL:
        return _epoch_cache["value"]
    from sqlalchemy import text

    from ..db import neon_engine

    value = _epoch_cache["value"]  # fail-open: keep last known if the DB read blips
    engine = neon_engine()
    if engine is not None:
        try:
            async with engine.connect() as conn:
                row = (await conn.execute(
                    text("SELECT last_synced_at FROM sync_state WHERE key = :k"),
                    {"k": _AUTH_EPOCH_KEY},
                )).first()
            value = row[0].timestamp() if row and row[0] else None
        except Exception:
            log.warning("auth epoch read failed — honouring token", exc_info=True)
    _epoch_cache.update(value=value, read_at=time.monotonic())
    return value


async def force_logout_all(actor_email: str) -> None:
    """Sign every user out (including the caller) by moving the session cutoff to now."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from ..db import neon_engine
    from ..models import SyncState

    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    now = datetime.now(timezone.utc)
    stmt = pg_insert(SyncState).values(
        key=_AUTH_EPOCH_KEY, last_synced_at=now, last_status="force_logout", detail=actor_email, row_count=None,
    ).on_conflict_do_update(
        index_elements=[SyncState.key],
        set_={"last_synced_at": now, "last_status": "force_logout", "detail": actor_email},
    )
    async with engine.begin() as conn:
        await conn.execute(stmt)
    _epoch_cache.update(value=now.timestamp(), read_at=time.monotonic())  # enforce instantly on this worker


async def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    settings = get_settings()
    if not settings.auth_enabled:
        return OPEN_USER
    if creds is None:
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        payload = jwt.decode(creds.credentials, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"invalid session: {e}")
    epoch = await _read_auth_epoch()
    if epoch is not None and payload.get("iat", 0) < epoch:
        raise HTTPException(status_code=401, detail="session ended — please sign in again")
    return {
        "id": payload["sub"], "email": payload["email"], "role": payload.get("role", "rm"),
        "name": payload.get("name"), "picture": payload.get("picture"),
        "assignment_name": payload.get("assignment_name"),
    }


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return user


def assignment_aliases(user: dict) -> list[str]:
    """Names this user is known by in the sheet's 'Assigned to' column — used to
    map leads to the user. Always derived from the user's name: matches on both the
    full name and the first name (the sheet uses first names like 'Dheeraj')."""
    name = (user.get("name") or "").strip()
    if not name:
        return []
    return list({name.lower(), name.split()[0].lower()})


def build_assignee_canon_map(users: list[dict]) -> dict[str, str]:
    """alias (lowercased) → the user's canonical full `name`. A lead's free-text
    `assigned_to` diverges by source — the sheet writes first names ('Saumya'),
    the in-app Assign button writes full names ('Saumya Behera') — so both must
    resolve to one owner. Each user contributes their full name, first name, and
    `assignment_name` as aliases; any alias that would collide across two different
    users is dropped, so an ambiguous first name is left untouched rather than
    mis-assigned."""
    from collections import defaultdict

    owners: dict[str, set[str]] = defaultdict(set)
    for u in users:
        full = (u.get("name") or "").strip()
        if not full:
            continue
        aliases = {full.lower(), full.split()[0].lower()}
        an = (u.get("assignment_name") or "").strip()
        if an:
            aliases.add(an.lower())
        for a in aliases:
            owners[a].add(full)
    return {alias: next(iter(names)) for alias, names in owners.items() if len(names) == 1}


def canonical_assignee(name: str | None, canon: dict[str, str]) -> str | None:
    """Resolve a raw assigned name to its canonical full name via `canon`; unknown
    names (e.g. the 'RM 1' test leads) pass through unchanged."""
    if not name:
        return name
    return canon.get(name.strip().lower(), name)
