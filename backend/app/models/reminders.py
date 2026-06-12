import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TZDateTime

REMINDER_TYPES = ("follow_up", "visit_schedule", "visit_feedback", "negotiation")


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        sa.CheckConstraint(
            "type IN ('follow_up','visit_schedule','visit_feedback','negotiation')",
            name="ck_reminders_type",
        ),
        sa.Index("ix_reminders_done_due_at", "done", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    due_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    done: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    auto_generated: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    # set by the scheduler once the due notification stub has fired
    notified: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    lead = relationship("Lead", lazy="selectin")
