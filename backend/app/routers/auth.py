from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.security import create_jwt, verify_google_token
from app.db import get_session
from app.models import User
from app.schemas.requests import DevLoginRequest, GoogleAuthRequest
from app.services.serializers import user_payload

router = APIRouter(tags=["auth"])


async def _login_by_email(session: AsyncSession, email: str) -> dict:
    user = (
        await session.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
    ).scalar_one_or_none()
    if user is None or not user.active:
        raise ApiError(403, "Account not provisioned")
    return {"token": create_jwt(user), "user": user_payload(user)}


@router.post("/auth/google")
async def auth_google(payload: GoogleAuthRequest, session: AsyncSession = Depends(get_session)):
    try:
        email = verify_google_token(payload.credential)
    except Exception:
        raise ApiError(401, "Invalid Google credential")
    return await _login_by_email(session, email)


@router.post("/auth/dev-login")
async def dev_login(payload: DevLoginRequest, session: AsyncSession = Depends(get_session)):
    if not settings.DEV_LOGIN_ENABLED:
        raise ApiError(404, "Not Found")
    return await _login_by_email(session, payload.email)


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return user_payload(user)
