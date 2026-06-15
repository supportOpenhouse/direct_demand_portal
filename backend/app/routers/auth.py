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
    settings = get_settings()
    if not settings.auth_enabled:
        raise HTTPException(status_code=400, detail="auth not configured")
    info = verify_google_token(payload.credential)
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    # first openhouse user becomes admin; everyone else defaults to rm
    async with engine.begin() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM users"))).scalar() or 0
        default_role = "admin" if count == 0 else "rm"
        stmt = pg_insert(User).values(
            email=info["email"], name=info["name"], picture=info["picture"],
            role=default_role, last_login_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=[User.email],
            set_={"name": info["name"], "picture": info["picture"], "last_login_at": datetime.now(timezone.utc)},
        ).returning(User.id, User.email, User.name, User.picture, User.role)
        row = (await conn.execute(stmt)).mappings().first()
    user = {"id": str(row["id"]), "email": row["email"], "name": row["name"],
            "picture": row["picture"], "role": row["role"]}
    return {"token": issue_jwt(user), "user": user}


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return user
