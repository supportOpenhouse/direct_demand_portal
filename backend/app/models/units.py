import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.utils import utcnow
from app.models.base import Base, TZDateTime

SUPPLY_STAGES = ("msi", "token_paid", "negotiating")


class Inventory(Base):
    """Acquired-property units (synced from Acquired Property Dashboard — stub)."""
    __tablename__ = "inventory"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    society: Mapped[str | None] = mapped_column(sa.String(160), nullable=True)
    city: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    budget_band: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    budget_min_lacs: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    budget_max_lacs: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    configuration: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    price_lacs: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    area_sqft: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    status: Mapped[str | None] = mapped_column(sa.String(32), nullable=True, default="available")
    lat: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    image_url: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    ext_source: Mapped[str] = mapped_column(sa.String(40), nullable=False, default="acquired_property")
    synced_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True, default=utcnow)


class SupplyUnit(Base):
    """Pipeline units (synced from Supply Closure Tracker — stub)."""
    __tablename__ = "supply_units"
    __table_args__ = (
        sa.CheckConstraint(
            "supply_stage IN ('msi','token_paid','negotiating')", name="ck_supply_stage"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    society: Mapped[str | None] = mapped_column(sa.String(160), nullable=True)
    city: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    budget_band: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    budget_min_lacs: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    budget_max_lacs: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    configuration: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    price_lacs: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    area_sqft: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    eta: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    supply_stage: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="msi")
    lat: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    image_url: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    ext_source: Mapped[str] = mapped_column(sa.String(40), nullable=False, default="supply_tracker")
    synced_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True, default=utcnow)


class Interest(Base):
    """\"I have a buyer\" tags against supply units."""
    __tablename__ = "interests"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    supply_unit_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("supply_units.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    rm_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, default=utcnow)
