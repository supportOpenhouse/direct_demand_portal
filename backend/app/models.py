"""Neon tables. Mapped columns are a projection of `raw` — the full sheet row
always lands in `raw` JSONB, so sheet column changes never break the sync."""
from sqlalchemy import BigInteger, Integer, Numeric, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InventoryUnit(Base):
    __tablename__ = "inventory_units"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    row_key: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    society: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    configuration: Mapped[str | None] = mapped_column(Text)
    area_sqft: Mapped[float | None] = mapped_column(Numeric)
    price_text: Mapped[str | None] = mapped_column(Text)
    price_lacs: Mapped[float | None] = mapped_column(Numeric)
    status: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    synced_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class SyncState(Base):
    __tablename__ = "sync_state"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    last_synced_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
