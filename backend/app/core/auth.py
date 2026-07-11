"""Google OAuth verification + app JWT.

Graceful: when GOOGLE_OAUTH_CLIENT_ID is unset, `current_user` returns a synthetic
admin so the API stays open (the live deployment never locks out until auth is
deliberately configured on both sides)."""
import logging
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
