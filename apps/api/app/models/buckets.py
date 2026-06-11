import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utcnow
from app.models.base import Base, JSONVariant, TZDateTime


class Bucket(Base):
    """Gold Mine: one bucket per inventory or supply unit."""
    __tablename__ = "buckets"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    inventory_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("inventory.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    supply_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("supply_units.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, default=utcnow)

    inventory = relationship("Inventory", lazy="selectin")
    supply_unit = relationship("SupplyUnit", lazy="selectin")
    members = relationship(
        "BucketMember", lazy="selectin", cascade="all, delete-orphan",
        order_by="BucketMember.score.desc()",
    )


class BucketMember(Base):
    __tablename__ = "bucket_members"
    # composite PK doubles as the unique (bucket_id, lead_id) constraint

    bucket_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("buckets.id", ondelete="CASCADE"), primary_key=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    matched_on: Mapped[list] = mapped_column(JSONVariant, nullable=False, default=list)

    lead = relationship("Lead", lazy="selectin")
