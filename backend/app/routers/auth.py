from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..core.auth import current_user, issue_jwt, verify_google_token
from ..db import neon_engine
from ..models import User

router = APIRouter(tags=["auth"])


class GoogleLogin(BaseModel):
    credential: str  # Google ID token from Google Identity Services


@router.get("/auth/config")
async def auth_config():
    """Lets the frontend learn whether to show the login gate."""
    s = get_settings()
    return {"enabled": s.auth_enabled, "client_id": s.GOOGLE_OAUTH_CLIENT_ID or None,
            "allowed_domain": s.ALLOWED_EMAIL_DOMAIN or None}


@router.post("/auth/google")
async def auth_google(payload: GoogleLogin):
    """Only pre-added (active) users may sign in. Bootstrap admins in
    INITIAL_ADMIN_EMAILS are auto-provisioned as admin on first sign-in."""
    settings = get_settings()
    if not settings.auth_enabled:
        raise HTTPException(status_code=400, detail="auth not configured")
    info = verify_google_token(payload.credential)
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    email = info["email"].lower()
    now = datetime.now(timezone.utc)
    async with engine.begin() as conn:
        existing = (await conn.execute(
            text("SELECT id, name, picture, role, assignment_name, active FROM users WHERE lower(email) = :e"),
            {"e": email},
        )).mappings().first()

        if existing:
            if not existing["active"]:
                raise HTTPException(status_code=403, detail="your account is disabled — contact an admin")
            await conn.execute(text("UPDATE users SET last_login_at = :t, picture = COALESCE(:p, picture) WHERE id = :id"),
                               {"t": now, "p": info["picture"], "id": existing["id"]})
            row = existing
        elif email in settings.initial_admins:
            stmt = pg_insert(User).values(
                email=info["email"], name=info["name"], picture=info["picture"], role="admin",
                assignment_name=(info["name"] or "").split()[0] if info.get("name") else None,
                last_login_at=now,
            ).returning(User.id, User.name, User.picture, User.role, User.assignment_name)
            row = (await conn.execute(stmt)).mappings().first()
        else:
            raise HTTPException(status_code=403, detail="not authorized — ask an admin to add you in Settings")

    user = {"id": str(row["id"]), "email": info["email"], "name": row["name"],
            "picture": info["picture"] or row.get("picture"), "role": row["role"],
            "assignment_name": row.get("assignment_name")}
    return {"token": issue_jwt(user), "user": user}


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return user
