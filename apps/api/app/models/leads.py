import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utcnow
from app.models.base import Base, TZDateTime

SOURCES = ("meta", "gads", "99acres", "magicbricks", "youtube", "whatsapp", "api", "webhook", "sheets")
STAGES = (
    "new", "contacted", "visit_scheduled", "visit_feedback", "negotiation",
    "won", "lost", "future_prospect", "timepass",
)
PLANS = ("within_30_days", "1_3_months", "3_6_months", "just_exploring")
PURPOSES = ("self_use", "investment")
OFFICE_WILLING = ("yes", "no", "maybe")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        sa.CheckConstraint(_in("source", SOURCES), name="ck_leads_source"),
        sa.CheckConstraint(_in("stage", STAGES), name="ck_leads_stage"),
        sa.Index("ix_leads_confirmed_qualified_at", "confirmed", "qualified_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    phone: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    source: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id"), nullable=True, index=True
    )
    stage: Mapped[str] = mapped_column(sa.String(24), nullable=False, default="new", index=True)
    tat_deadline: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    confirmed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    qualified_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    is_hot: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    city: Mapped[str | None] = mapped_column(sa.String(80), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    assignee = relationship("User", lazy="selectin", foreign_keys=[assigned_to])
    source_data = relationship(
        "LeadSourceData", lazy="selectin", uselist=False, cascade="all, delete-orphan"
    )
    confirmed_data = relationship(
        "LeadConfirmedData", lazy="selectin", uselist=False, cascade="all, delete-orphan"
    )
    shortlist_societies = relationship(
        "LeadShortlistSociety", lazy="selectin", cascade="all, delete-orphan"
    )
    preferred_localities = relationship(
        "LeadPreferredLocality", lazy="selectin", cascade="all, delete-orphan"
    )
    activities = relationship(
        "LeadActivity", lazy="selectin", cascade="all, delete-orphan",
        order_by="LeadActivity.created_at.desc()",
    )
    recordings = relationship(
        "Recording", lazy="selectin", cascade="all, delete-orphan",
        order_by="Recording.recorded_at.desc()",
    )
    visits = relationship(
        "Visit", lazy="selectin", cascade="all, delete-orphan",
        order_by="Visit.trip_date.desc()",
    )


class LeadSourceData(Base):
    """Source-captured layer — ADMIN-write only."""
    __tablename__ = "lead_source_data"
    __table_args__ = (
        sa.CheckConstraint(f"plan_to_buy IS NULL OR {_in('plan_to_buy', PLANS)}", name="ck_lsd_plan"),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )
    budget_band: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    budget_min_lacs: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    budget_max_lacs: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    city: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    society: Mapped[str | None] = mapped_column(sa.String(160), nullable=True)
    configuration: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    plan_to_buy: Mapped[str | None] = mapped_column(sa.String(24), nullable=True)


class LeadConfirmedData(Base):
    """Confirmed-on-call layer (Q1-Q6)."""
    __tablename__ = "lead_confirmed_data"
    __table_args__ = (
        sa.CheckConstraint(f"purpose IS NULL OR {_in('purpose', PURPOSES)}", name="ck_lcd_purpose"),
        sa.CheckConstraint(
            f"office_willing IS NULL OR {_in('office_willing', OFFICE_WILLING)}", name="ck_lcd_office"
        ),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )
    purpose: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    budget_value_lacs: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    configuration: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    office_willing: Mapped[str | None] = mapped_column(sa.String(8), nullable=True)
    office_preferred_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    remark: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)


class LeadShortlistSociety(Base):
    """Q4 multi-select."""
    __tablename__ = "lead_shortlist_societies"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )
    society: Mapped[str] = mapped_column(sa.String(160), primary_key=True)


class LeadPreferredLocality(Base):
    """Q5 multi-select."""
    __tablename__ = "lead_preferred_localities"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )
    locality: Mapped[str] = mapped_column(sa.String(160), primary_key=True)


class LeadActivity(Base):
    __tablename__ = "lead_activity"
    __table_args__ = (
        sa.Index("ix_lead_activity_lead_created", "lead_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    remark: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, sa.ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, default=utcnow)

    actor = relationship("User", lazy="selectin", foreign_keys=[actor_id])
