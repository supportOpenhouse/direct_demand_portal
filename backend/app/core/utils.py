from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current UTC time. Always use this, never datetime.utcnow()."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Attach UTC to naive datetimes (SQLite round-trips drop tzinfo) before comparing."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
