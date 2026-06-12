import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utcnow
from app.models.base import Base, TZDateTime


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(120), unique=True, nullable=False)
    # Logical FK -> users.id. No DB constraint to avoid the users<->teams cycle
    # (SQLite cannot ALTER TABLE ADD CONSTRAINT); enforced in app code.
    cm_user_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint("role IN ('admin','cm','rm')", name="ck_users_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    email: Mapped[str] = mapped_column(sa.String(254), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, sa.ForeignKey("teams.id"), nullable=True)
    active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, default=utcnow)

    team: Mapped[Team | None] = relationship("Team", lazy="selectin", foreign_keys=[team_id])
