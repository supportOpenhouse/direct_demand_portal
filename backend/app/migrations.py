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
    ("meta_leads", "city", "TEXT"),
    ("meta_leads", "society", "TEXT"),
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
    # call worklist / follow-up flow
    ("leads", "follow_up_at", "TIMESTAMPTZ"),
    ("leads", "miss_count", "INTEGER NOT NULL DEFAULT 0"),
    ("leads", "ever_connected", "BOOLEAN NOT NULL DEFAULT false"),
    # when the lead first entered the Follow-up worklist (set on NULL→value, cleared
    # when it leaves) — drives the "moved here today" highlight
    ("leads", "follow_up_since", "TIMESTAMPTZ"),
    ("leads", "is_hot", "BOOLEAN NOT NULL DEFAULT false"),
    # WhatsApp media — wa_messages predates these, so create_all() won't add them
    ("wa_messages", "media_url", "TEXT"),
    ("wa_messages", "media_expiry", "TIMESTAMPTZ"),
    ("wa_messages", "media_name", "TEXT"),
    # spam guard on the call worklist's "No"
    ("leads", "last_no_timestamp", "TIMESTAMPTZ"),
    # click-to-call rings the RM's own handset first
    ("users", "phone", "TEXT"),
    # WhatsApp conversation ownership (round-robin across active RMs)
    ("wa_contacts", "assigned_to", "TEXT"),
    ("wa_contacts", "assigned_at", "TIMESTAMPTZ"),
    # visit planner: `rm` split into the lead's RM and whoever accompanies the visit
    ("visits", "lead_rm", "TEXT"),
    ("visits", "rm_accompanying", "TEXT"),
    # auto-dialer: connected/not for each attempt, filled by the callback or the poller
    ("dial_queue", "answered", "BOOLEAN NOT NULL DEFAULT false"),
    # which campaign placed a call — lets Previous Campaigns list every call it made,
    # retries included, after dial_queue has moved on to a new event_id
    ("call_logs", "campaign_id", "UUID"),
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
    from .core.auth import build_assignee_canon_map, canonical_assignee
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

            # back-fill WhatsApp media off the stored callback. Messages received
            # before the media columns existed rendered as a bare "[audio]", but the
            # whole payload was kept in raw — so the download link is recoverable.
            # (Whether it still resolves depends on urlExpiry; the UI says which.)
            await conn.execute(text("""
                UPDATE wa_messages SET
                  media_url  = raw->'payload'->'payload'->>'url',
                  media_name = raw->'payload'->'payload'->>'name',
                  media_expiry = CASE
                    WHEN (raw->'payload'->'payload'->>'urlExpiry') ~ '^[0-9]+$'
                    THEN to_timestamp((raw->'payload'->'payload'->>'urlExpiry')::bigint / 1000.0)
                  END
                WHERE media_url IS NULL
                  AND raw->'payload'->'payload'->>'url' IS NOT NULL
            """))

            # --- stage model: `stage` is now authoritative for which page a lead is on
            # (see docs/superpowers/specs/2026-07-29-lead-stage-model-design.md).
            # Idempotent: after one run nothing matches, so re-running is a no-op.
            #   contacted + visit_planned  → qualified   (these ARE the qualified leads)
            #   new with an open callback  → call_not_received / follow_up, split on
            #                                whether we ever reached them. Without this
            #                                they'd land back on New — they're in
            #                                Follow-up today.
            #   lost/future_prospect/timepass → rejected (declared in code, zero rows)
            await conn.execute(text(
                "UPDATE leads SET stage = 'qualified' WHERE stage IN ('contacted','visit_planned')"))
            await conn.execute(text(
                "UPDATE leads SET stage = 'call_not_received' "
                "WHERE stage = 'new' AND follow_up_at IS NOT NULL AND NOT ever_connected"))
            await conn.execute(text(
                "UPDATE leads SET stage = 'follow_up' "
                "WHERE stage = 'new' AND follow_up_at IS NOT NULL AND ever_connected"))
            await conn.execute(text(
                "UPDATE leads SET stage = 'rejected' "
                "WHERE stage IN ('lost','future_prospect','timepass')"))

            # tag became nullable when assignment arrived — a contact can have an
            # owner before anyone classifies it
            await conn.execute(text("ALTER TABLE wa_contacts ALTER COLUMN tag DROP NOT NULL"))

            # attribute past dialer calls to their campaign. Only the attempt whose
            # event_id is still on the queue row is recoverable: a retry NULLs it
            # (services/dialer.py), so earlier attempts of finished campaigns stay
            # unattributed for good. Everything placed from here on is exact.
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_call_logs_campaign_id
                    ON call_logs (campaign_id)"""))
            await conn.execute(text("""
                UPDATE call_logs c SET campaign_id = q.campaign_id
                  FROM dial_queue q
                 WHERE q.event_id = c.event_id AND c.campaign_id IS NULL"""))

            # seed the split visit-RM columns from the single field they replace: the
            # stored value was the lead's RM, and the accompanying RM defaults to the
            # same person. Only fills NULLs, so hand-picked values survive.
            await conn.execute(text(
                "UPDATE visits SET lead_rm = rm WHERE lead_rm IS NULL AND rm IS NOT NULL"))
            await conn.execute(text(
                "UPDATE visits SET rm_accompanying = rm "
                "WHERE rm_accompanying IS NULL AND rm IS NOT NULL"))

            # seed Openhouse SalesManager ids (smid) for the booking team by name —
            # only fills blanks, so admin edits via Settings are never clobbered. Runs
            # every boot, so a seed user added later still gets mapped on next deploy.
            for full_name, smid in SMID_SEED.items():
                await conn.execute(text(
                    "UPDATE users SET smid = :smid WHERE smid IS NULL AND "
                    "(lower(name) = lower(:full) OR lower(split_part(name, ' ', 1)) = lower(:fn))"),
                    {"smid": smid, "full": full_name, "fn": full_name.split()[0]})

            # canonicalize lead owners: the sheet writes first names ('Saumya') and
            # the app writes full names ('Saumya Behera'), so one person shows up as
            # two owners in filters/analytics. Rewrite every alias to the user's full
            # name (idempotent — a canonical value resolves to itself; ambiguous first
            # names are left alone by build_assignee_canon_map).
            urows = await conn.execute(text(
                "SELECT name, assignment_name FROM users WHERE active AND name IS NOT NULL"))
            canon = build_assignee_canon_map([dict(r) for r in urows.mappings()])
            dvals = await conn.execute(text(
                "SELECT DISTINCT assigned_to FROM leads WHERE assigned_to IS NOT NULL"))
            for (raw,) in dvals:
                target = canonical_assignee(raw, canon)
                if target and target != raw:
                    await conn.execute(
                        text("UPDATE leads SET assigned_to = :t WHERE assigned_to = :r"),
                        {"t": target, "r": raw})

            # canonicalize existing lead cities (the cron is insert-only, so it won't
            # re-normalize old rows; inventory self-heals on sync, supply is live)
            await conn.execute(text("UPDATE leads SET city='Noida' WHERE city ILIKE '%noida%' AND city <> 'Noida'"))
            await conn.execute(text("UPDATE leads SET city='Gurgaon' WHERE (city ILIKE '%gurgaon%' OR city ILIKE '%gurugram%') AND city <> 'Gurgaon'"))
            await conn.execute(text("UPDATE leads SET city='Ghaziabad' WHERE city ILIKE '%ghaziabad%' AND city <> 'Ghaziabad'"))
        log.info("migrations applied (%d listing dates back-filled)", len(updates))
    except Exception:
        log.exception("migrations failed — continuing (additive only)")
