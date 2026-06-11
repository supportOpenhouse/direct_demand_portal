"""Declarative base + dialect-portable column types.

Everything must run on both SQLite (local dev / pytest) and Postgres (Neon prod):
- sa.Uuid for ids (CHAR(32) on SQLite, native uuid on Postgres)
- TZDateTime: timezone-aware UTC in / out on both dialects (SQLite drops tzinfo
  on storage, so the result processor re-attaches UTC)
- JSONVariant: plain JSON with a JSONB variant on Postgres
"""
from datetime import timezone

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class TZDateTime(sa.TypeDecorator):
    impl = sa.DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            # SQLite stores a fixed-width naive string; keep it canonical UTC.
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


JSONVariant = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
