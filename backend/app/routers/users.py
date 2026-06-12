import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.core.errors import ApiError
from app.db import get_session
from app.models import Team, User
from app.schemas.requests import UserCreate
from app.services.serializers import user_payload

router = APIRouter(tags=["users"], dependencies=[Depends(require_roles("admin"))])


@router.get("/users")
async def list_users(session: AsyncSession = Depends(get_session)):
    users = (await session.execute(select(User).order_by(User.created_at.asc()))).scalars().all()
    return [user_payload(u) for u in users]


@router.post("/users", status_code=201)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    email = payload.email.strip().lower()
    existing = (
        await session.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise ApiError(422, "Validation error", {"email": "A user with this email already exists"})
    if payload.team_id is not None:
        team = await session.get(Team, payload.team_id)
        if team is None:
            raise ApiError(422, "Validation error", {"team_id": "Unknown team"})
    user = User(
        id=uuid.uuid4(),
        name=payload.name.strip(),
        email=email,
        phone=payload.phone,
        role=payload.role,
        team_id=payload.team_id,
        active=True,
    )
    session.add(user)
    await session.commit()
    user = (
        await session.execute(
            select(User).where(User.id == user.id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    return user_payload(user)
