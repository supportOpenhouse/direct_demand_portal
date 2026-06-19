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
    ("users", "smid", "INTEGER"),
    ("lead_confirmed_data", "budget_min_lacs", "NUMERIC"),
    ("lead_confirmed_data", "budget_max_lacs", "NUMERIC"),
    ("lead_confirmed_data", "size_sqft", "NUMERIC"),
    ("lead_confirmed_data", "size_min_sqft", "NUMERIC"),
    ("lead_confirmed_data", "size_max_sqft", "NUMERIC"),
    ("lead_confirmed_data", "preferred_micromarkets", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
    ("inventory_units", "lat", "NUMERIC"),
    ("inventory_units", "lng", "NUMERIC"),
    ("leads", "reject_reason", "TEXT"),
    ("leads", "reject_notes", "TEXT"),
    ("leads", "rejected_at", "TIMESTAMPTZ"),
]

# Openhouse Core SalesManager.id per booking-team member (name → smid)
SMID_SEED = {
    "Saransh": 82,
    "Saumya Behera": 30,
    "Varun Matrey": 97,
    "Rahul Singh": 83,
    "Ashish": 105,
}


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

            # seed Openhouse SalesManager ids (smid) for the booking team by name —
            # only fills blanks, so admin edits via Settings are never clobbered. Runs
            # every boot, so a seed user added later still gets mapped on next deploy.
            for full_name, smid in SMID_SEED.items():
                await conn.execute(text(
                    "UPDATE users SET smid = :smid WHERE smid IS NULL AND "
                    "(lower(name) = lower(:full) OR lower(split_part(name, ' ', 1)) = lower(:fn))"),
                    {"smid": smid, "full": full_name, "fn": full_name.split()[0]})

            # canonicalize existing lead cities (the cron is insert-only, so it won't
            # re-normalize old rows; inventory self-heals on sync, supply is live)
            await conn.execute(text("UPDATE leads SET city='Noida' WHERE city ILIKE '%noida%' AND city <> 'Noida'"))
            await conn.execute(text("UPDATE leads SET city='Gurgaon' WHERE (city ILIKE '%gurgaon%' OR city ILIKE '%gurugram%') AND city <> 'Gurgaon'"))
            await conn.execute(text("UPDATE leads SET city='Ghaziabad' WHERE city ILIKE '%ghaziabad%' AND city <> 'Ghaziabad'"))
        log.info("migrations applied (%d listing dates back-filled)", len(updates))
    except Exception:
        log.exception("migrations failed — continuing (additive only)")
