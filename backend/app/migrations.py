"""Lightweight idempotent migrations run at startup.

create_all() creates missing tables but never ALTERs existing ones, and the
leads tables already hold production data — so additive column changes go here as
`ADD COLUMN IF NOT EXISTS`. Safe to run on every boot.
"""
import logging

from sqlalchemy import text

log = logging.getLogger("migrations")

# (table, column, type) — additive only
_ADD_COLUMNS = [
    ("leads", "received_at", "TIMESTAMPTZ"),
    ("users", "assignment_name", "TEXT"),
    ("users", "active", "BOOLEAN NOT NULL DEFAULT true"),
]


async def run_migrations(engine) -> None:
    if engine is None:
        return
    from .services.leads_sync import parse_lead_date

    try:
        async with engine.begin() as conn:
            for table, col, coltype in _ADD_COLUMNS:
                await conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}'))

            # one-time back-fill of listing leads' real source date from the raw table
            # (the cron is insert-only, so existing spine rows never get updated by it)
            rows = await conn.execute(text(
                "SELECT dedupe_key, lead_date FROM listing_leads WHERE lead_date IS NOT NULL"
            ))
            updates = []
            for dk, raw in rows:
                parsed = parse_lead_date(raw)
                if parsed:
                    updates.append({"ok": "listing:" + dk, "ts": parsed})
            for u in updates:
                await conn.execute(
                    text("UPDATE leads SET received_at = :ts WHERE origin_key = :ok "
                         "AND (received_at IS NULL OR received_at = created_at)"),
                    u,
                )
            # everything still null (meta has no source date) → use ingest time
            await conn.execute(text("UPDATE leads SET received_at = created_at WHERE received_at IS NULL"))
        log.info("migrations applied (%d listing dates back-filled)", len(updates))
    except Exception:
        log.exception("migrations failed — continuing (additive only)")
