"""Backfill a Huvo call export into huvo_call_updates.

    uv run python scripts/import_huvo_csv.py ../leads-2026-08-13.csv           # dry run
    uv run python scripts/import_huvo_csv.py ../leads-2026-08-13.csv --apply   # write

Dry run by default. This writes to the live leads database, and a 1399-row insert is
not something to discover was wrong afterwards.

Safe to re-run: rows are keyed by the same dedupe_key the live webhook uses
(routers/huvo.py), so an import that half-finished, or an export that overlaps calls
already received, inserts only what's genuinely new.

Three things about the export that the mapping has to respect:

  * `Call Date` is the call's start — it matches the dedupe_key of a row Huvo already
    delivered. `Created At` is when Huvo wrote the record, so it maps to received_at.
  * Every date-ish analytics field is prose ("two o'clock", "unsure"). There is no ISO
    `_dt` column anywhere in the export, so follow_up_at stays NULL. Parsing a
    follow-up out of "two o'clock" would put a real callback in an RM's queue at an
    invented time.
  * Three headers repeat, and `Site Visit Schedule` repeats with DIFFERENT data in
    each (247 rows filled vs 236). csv.DictReader keeps only the last, so this reads
    by column index and keeps both.
"""
import argparse
import asyncio
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.db import dispose_engines, neon_engine  # noqa: E402
from app.services.huvo import _budget_lacs, dedupe_key, digits10  # noqa: E402

# Columns not in Huvo's webhook schema. Kept under payload._import.extra rather than
# dropped — the same raw-first reasoning the table itself is built on.
EXTRA_COLS = ("Campaign", "All Phones", "Agent Name", "Sentiment", "Lead Status",
              "Whatsapp", "Visit Datetime", "Site Visit Date")

_INSERT = text("""
    INSERT INTO huvo_call_updates
           (id, dedupe_key, lead_id, from_number, caller_name, call_outcome,
            is_interested, rsvp_status, lead_score, budget_lacs, summary,
            recording_url, duration_sec, started_at, ended_at, follow_up_at,
            payload, received_at)
    VALUES (gen_random_uuid(), :dedupe_key, :lead_id, :from_number, :caller_name,
            :call_outcome, :is_interested, :rsvp_status, :lead_score, :budget_lacs,
            :summary, NULL, :duration_sec, :started_at, NULL, NULL,
            CAST(:payload AS jsonb), COALESCE(CAST(:received_at AS timestamptz), now()))
    -- no RETURNING: this runs as one executemany, where asyncpg can't hand back a row
    -- per statement. The count difference tells us what landed.
    ON CONFLICT (dedupe_key) DO NOTHING
""")

# Every phone -> its one best lead, in a single read.
#
# routers/huvo.py resolves this per call, which is right for one webhook and wrong for
# 1399 rows: that's 1399 round trips to a database in Singapore, and the first version
# of this script took longer than two minutes before it wrote anything.
#
# DISTINCT ON encodes the same preference the webhook uses — a number can belong to
# more than one lead (~5% here), so prefer one still in play over one already closed
# out, then the most recent.
_ALL_LEAD_PHONES = text("""
    SELECT DISTINCT ON (right(regexp_replace(phone, '[^0-9]', '', 'g'), 10))
           right(regexp_replace(phone, '[^0-9]', '', 'g'), 10) AS phone10, id
      FROM leads
     WHERE phone IS NOT NULL
     ORDER BY phone10, (stage IN ('won','rejected','rnr')), created_at DESC
""")


def read_rows(path: Path) -> list[dict]:
    """Rows as dicts, reading by index so repeated headers both survive.

    A repeated name gets a numeric suffix for the later occurrences, so
    'Site Visit Schedule' and 'Site Visit Schedule#2' are both addressable.
    """
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        seen: Counter = Counter()
        names = []
        for h in header:
            seen[h] += 1
            names.append(h if seen[h] == 1 else f"{h}#{seen[h]}")
        return [dict(zip(names, row)) for row in reader if any(c.strip() for c in row)]


def clean(value) -> str | None:
    """Blank cells are absent data, not empty strings."""
    text_value = (value or "").strip()
    return text_value or None


def to_int(value) -> int | None:
    try:
        return int(float(clean(value)))
    except (TypeError, ValueError):
        return None


def to_float(value) -> float | None:
    try:
        return float(clean(value))
    except (TypeError, ValueError):
        return None


def to_dt(value) -> datetime | None:
    """ISO-8601 -> datetime, else None.

    A real datetime, not a string: this inserts via executemany, where asyncpg binds
    parameters itself and never sees the statement's CAST — a string reaches the
    driver as a string and is rejected against a timestamptz column.

    The export's date-ish fields are mostly prose ("two o'clock", "unsure"), so most
    of these correctly return None rather than a guess.
    """
    raw = clean(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def build(row: dict, source_file: str) -> dict:
    """One CSV row -> the columns huvo_call_updates takes, plus a reconstructed
    envelope in the exact shape the live webhook stores."""
    number = digits10(row.get("Primary Phone"))
    started = to_dt(row.get("Call Date"))
    # The envelope carries the ISO string Huvo would have sent, so dedupe_key comes
    # out identical to one built from a live delivery of the same call.
    started_iso = started.isoformat() if started else None

    analytics = {
        "project_name": clean(row.get("Project")),
        "name": clean(row.get("Lead Name")),
        "from_number": clean(row.get("Primary Phone")),
        "lead_score": to_float(row.get("Lead Score")),
        "is_interested": clean(row.get("Interested")),
        "interest_reason": clean(row.get("Interest Reason")),
        "type_of_property": clean(row.get("Type Of Property")) or clean(row.get("Property Type")),
        "purpose": clean(row.get("Purpose")),
        "location": clean(row.get("Location")),
        "budget_crores": clean(row.get("Budget (Cr)")),
        "site_visit_schedule": clean(row.get("Site Visit Schedule")),
        "call_outcome_schedule": clean(row.get("Call Outcome Schedule")),
        # no ISO column exists in the export — see the module docstring
        "call_outcome_schedule_dt": None,
        "follow_up_time": clean(row.get("Follow Up Time")) or clean(row.get("Follow-up Time")),
        "follow_up_time_dt": None,
        "summary_of_call": clean(row.get("Summary")),
        "call_outcome": clean(row.get("Call Outcome")),
        "rsvp_status": clean(row.get("Rsvp Status")) or clean(row.get("RSVP")),
        "callback_owner": clean(row.get("Callback Owner")),
    }
    envelope = {
        "status": "completed",
        "call_details": {
            "start_time": started_iso,
            "end_time": None,       # not present in the export
            "duration_sec": to_int(row.get("Call Duration (sec)")),
            "recording_url": None,  # not present in the export
            "summary": clean(row.get("Summary")),
        },
        "analytics_data": analytics,
        # provenance, so a backfilled row is always distinguishable from a delivered one
        "_import": {
            "source_file": source_file,
            "extra": {k: clean(row.get(k)) for k in EXTRA_COLS if clean(row.get(k))},
        },
    }
    return {
        "dedupe_key": dedupe_key(envelope),
        "from_number": number or None,
        "caller_name": analytics["name"],
        "call_outcome": analytics["call_outcome"],
        "is_interested": analytics["is_interested"],
        "rsvp_status": analytics["rsvp_status"],
        "lead_score": analytics["lead_score"],
        "budget_lacs": _budget_lacs(analytics["budget_crores"]),
        "summary": analytics["summary_of_call"],
        "duration_sec": envelope["call_details"]["duration_sec"],
        "started_at": started,
        "received_at": to_dt(row.get("Created At")),
        "payload": json.dumps(envelope, default=str),
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--apply", action="store_true",
                    help="actually write. Without it, nothing is inserted.")
    ap.add_argument("--only-called", action="store_true",
                    help="skip rows with no call outcome (they record no call)")
    args = ap.parse_args()

    rows = read_rows(args.csv_path)
    built = [build(r, args.csv_path.name) for r in rows]
    if args.only_called:
        built = [b for b in built if b["call_outcome"]]

    engine = neon_engine()
    if engine is None:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2

    inserted = 0
    async with engine.begin() as conn:
        by_phone = dict((await conn.execute(_ALL_LEAD_PHONES)).all())
        for row in built:
            row["lead_id"] = by_phone.get(row["from_number"] or "")
        matched = sum(1 for b in built if b["lead_id"])

        before = (await conn.execute(text("SELECT count(*) FROM huvo_call_updates"))).scalar()
        if args.apply and built:
            # One executemany rather than 1399 statements. ON CONFLICT DO NOTHING means
            # RETURNING can't tell us per row what landed, so the count difference does.
            await conn.execute(_INSERT, built)
        total = (await conn.execute(text("SELECT count(*) FROM huvo_call_updates"))).scalar()
        inserted = total - before
        skipped = len(built) - inserted if args.apply else 0

    print(f"rows read            : {len(rows)}")
    print(f"rows to import       : {len(built)}")
    print(f"  with a call outcome: {sum(1 for b in built if b['call_outcome'])}")
    print(f"  with a start time  : {sum(1 for b in built if b['started_at'])}")
    print(f"  matched to a lead  : {matched}")
    if args.apply:
        print(f"inserted             : {inserted}")
        print(f"already present      : {skipped}")
    else:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
    print(f"table row count now  : {total}")
    await dispose_engines()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
