import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utcnow
from app.models.base import Base, TZDateTime


class Visit(Base):
    __tablename__ = "visits"
    __table_args__ = (
        sa.CheckConstraint("route_source IN ('est','google')", name="ck_visits_route_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    trip_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    rm_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id"), nullable=True)
    total_km: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    total_min: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    route_source: Mapped[str] = mapped_column(sa.String(8), nullable=False, default="est")
    self_schedule_token: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(24), nullable=False, default="planned")

    rm = relationship("User", lazy="selectin", foreign_keys=[rm_id])
    stops = relationship(
        "VisitStop", lazy="selectin", cascade="all, delete-orphan", order_by="VisitStop.seq"
    )


class VisitStop(Base):
    __tablename__ = "visit_stops"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False
    )
    inventory_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("inventory.id"), nullable=False
    )
    seq: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    inventory = relationship("Inventory", lazy="selectin")


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    visit_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("visits.id", ondelete="SET NULL"), nullable=True
    )
    file_ref: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    duration_sec: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id"), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, default=utcnow)

    recorded_by_user = relationship("User", lazy="selectin", foreign_keys=[recorded_by])
