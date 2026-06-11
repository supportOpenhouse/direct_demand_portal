import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utcnow
from app.models.base import Base, JSONVariant, TZDateTime


class SocietyInsight(Base):
    __tablename__ = "society_insights"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    society: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    city: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    note: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, default=utcnow)

    creator = relationship("User", lazy="selectin", foreign_keys=[created_by])


class Society(Base):
    """Reference list for Q4 / inventory."""
    __tablename__ = "societies"
    __table_args__ = (sa.UniqueConstraint("name", "city", name="uq_societies_name_city"),)

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    city: Mapped[str] = mapped_column(sa.String(80), nullable=False)


class Locality(Base):
    """Reference list for Q5."""
    __tablename__ = "localities"
    __table_args__ = (sa.UniqueConstraint("name", "city", name="uq_localities_name_city"),)

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    city: Mapped[str] = mapped_column(sa.String(80), nullable=False)


class SettingsIntegration(Base):
    __tablename__ = "settings_integrations"

    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    hash: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    revoked: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, default=utcnow)
