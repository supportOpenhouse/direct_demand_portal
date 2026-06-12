import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_jwt
from app.core.utils import utcnow
from app.db import get_session
from app.main import app
from app.models import Base, Lead, LeadSourceData, Team, User


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def users(session):
    team = Team(name="Team Gurgaon")
    session.add(team)
    await session.flush()

    admin = User(name="Admin A", email="admin@test.local", role="admin")
    cm = User(name="CM C", email="cm@test.local", role="cm", team_id=team.id)
    rm1 = User(name="RM One", email="rm1@test.local", role="rm", team_id=team.id)
    rm2 = User(name="RM Two", email="rm2@test.local", role="rm", team_id=team.id)
    rm3 = User(name="RM Three", email="rm3@test.local", role="rm", team_id=None)
    session.add_all([admin, cm, rm1, rm2, rm3])
    await session.commit()
    team.cm_user_id = cm.id
    await session.commit()
    return SimpleNamespace(team=team, admin=admin, cm=cm, rm1=rm1, rm2=rm2, rm3=rm3)


@pytest.fixture
def auth():
    def _auth(user) -> dict:
        return {"Authorization": f"Bearer {create_jwt(user)}"}

    return _auth


@pytest.fixture
def make_lead(session):
    counter = {"n": 0}

    async def _make_lead(
        *,
        assigned_to: uuid.UUID | None,
        name: str = "Test Lead",
        source: str = "meta",
        stage: str = "new",
        confirmed: bool = False,
        qualified_at: datetime | None = None,
        city: str | None = "Gurgaon",
        society: str | None = "DLF The Crest",
        configuration: str | None = "3 BHK",
        budget_min_lacs: float | None = 80.0,
        budget_max_lacs: float | None = 100.0,
        plan_to_buy: str | None = None,
        created_at: datetime | None = None,
        tat_deadline: datetime | None = None,
        is_hot: bool = False,
    ) -> Lead:
        counter["n"] += 1
        created = created_at or utcnow()
        lead = Lead(
            name=name,
            phone=f"+91 90000{counter['n']:05d}",
            source=source,
            assigned_to=assigned_to,
            stage=stage,
            confirmed=confirmed,
            qualified_at=qualified_at,
            tat_deadline=tat_deadline if tat_deadline is not None else (
                None if confirmed else created + timedelta(minutes=60)
            ),
            is_hot=is_hot,
            city=city,
            created_at=created,
        )
        session.add(lead)
        await session.flush()
        session.add(
            LeadSourceData(
                lead_id=lead.id,
                city=city,
                society=society,
                configuration=configuration,
                budget_min_lacs=budget_min_lacs,
                budget_max_lacs=budget_max_lacs,
                plan_to_buy=plan_to_buy,
            )
        )
        await session.commit()
        return lead

    return _make_lead
