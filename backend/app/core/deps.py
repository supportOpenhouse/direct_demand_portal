import uuid

import sqlalchemy as sa
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import decode_jwt
from app.db import get_session
from app.models import Lead, User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if creds is None:
        raise ApiError(401, "Not authenticated")
    try:
        payload = decode_jwt(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        raise ApiError(401, "Invalid or expired token")
    user = await session.get(User, user_id)
    if user is None or not user.active:
        raise ApiError(401, "Invalid or expired token")
    return user


def require_roles(*roles: str):
    async def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise ApiError(403, "Forbidden")
        return user

    return dep


def lead_scope_filter(user: User) -> sa.ColumnElement | None:
    """SQL criterion limiting lead visibility per role.

    admin -> None (no filter); cm -> assigned_to IN (user ids in my team);
    rm -> assigned_to == me. Inject into EVERY lead-touching query.
    """
    if user.role == "admin":
        return None
    if user.role == "cm":
        if user.team_id is None:
            return Lead.assigned_to == user.id
        team_ids = select(User.id).where(User.team_id == user.team_id)
        return Lead.assigned_to.in_(team_ids)
    return Lead.assigned_to == user.id


def apply_lead_scope(stmt, user: User):
    crit = lead_scope_filter(user)
    return stmt if crit is None else stmt.where(crit)
