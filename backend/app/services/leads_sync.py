"""Leads ingest — reads the two source worksheets and adds NEW leads only.

INSERT-ONLY by design: the 4-hourly cron never updates or deletes. Each raw row
lands in its source table (meta_leads / listing_leads) keyed by a unique
normalized-phone dedupe_key (ON CONFLICT DO NOTHING), and a matching row is
created in the unified `leads` spine the same way. Re-running is therefore safe
and idempotent — already-seen leads are skipped.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..core.auth import build_assignee_canon_map, canonical_assignee
from ..db import neon_engine
from ..models import Lead, ListingLead, MetaLead, SyncState
from .normalize import normalize_city

log = logging.getLogger("leads_sync")


async def _write_state(key: str, status: str, detail: str | None, row_count: int | None) -> None:
    """Upsert a sync_state row (one per worksheet). Never raises."""
    engine = neon_engine()
    if engine is None:
        return
    stmt = pg_insert(SyncState).values(
        key=key,
        last_synced_at=datetime.now(timezone.utc) if status == "ok" else None,
        last_status=status,
        detail=detail,
        row_count=row_count,
    )
    update_set = {"last_status": stmt.excluded.last_status, "detail": stmt.excluded.detail,
                  "row_count": stmt.excluded.row_count}
    if status == "ok":
        update_set["last_synced_at"] = stmt.excluded.last_synced_at
    stmt = stmt.on_conflict_do_update(index_elements=[SyncState.key], set_=update_set)
    try:
        async with engine.begin() as conn:
            await conn.execute(stmt)
    except Exception:
        log.exception("failed to persist sync_state for %s", key)

LISTING_KEY = "listing_leads_sheet"
META_KEY = "meta_leads_sheet"

# 1-hour first-contact TAT, same rule as the prototype/HANDOVER §6.2
TAT_HOURS = 1

# ---- normalization helpers ----------------------------------------------------


def norm_phone(raw: str | None) -> str | None:
    """'p:+919953998821' / '91-9971652700' -> last 10 digits ('9953998821')."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) >= 10:
        return digits[-10:]
    return digits or None


def display_phone(norm: str | None) -> str | None:
    if not norm or len(norm) != 10:
        return norm
    return f"+91 {norm[:5]} {norm[5:]}"


def clean_name(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.strip().lstrip("@").replace("_", " ").strip() or None


SOURCE_MAP = {
    "99acre": "99acres",
    "99acres": "99acres",
    "magicbricks": "magicbricks",
    "magic bricks": "magicbricks",
}


def map_source(raw: str | None) -> str:
    return SOURCE_MAP.get((raw or "").strip().lower(), (raw or "").strip().lower() or "99acres")


def pretty_enum(raw: str | None) -> str | None:
    """'up_to_₹75_lacs' -> 'Up to ₹75 lacs'; 'within_30_days' -> 'Within 30 days'."""
    if not raw:
        return None
    s = raw.replace("_", " ").replace("–", "–").strip()
    s = re.sub(r"\s+", " ", s)
    return s[:1].upper() + s[1:] if s else None


# map Meta's plan-to-buy values onto the prototype's PLAN_OPTS so the chip colors match
PLAN_MAP = {
    "within 30 days": "Within 30 days",
    "1 – 3 months": "1–3 months",
    "1–3 months": "1–3 months",
    "3 – 6 months": "3–6 months",
    "3–6 months": "3–6 months",
    "just exploring": "Just exploring",
}


def map_plan(raw: str | None) -> str | None:
    p = pretty_enum(raw)
    return PLAN_MAP.get((p or "").lower(), p)


def _norm_header(h: str) -> str:
    return re.sub(r"[^\w]+", "_", h.strip().lower()).strip("_")


# listing sheet dates are MM/DD/YYYY (confirmed: '06/01/2026' co-occurs with 'Jun 1, 2026')
_DATE_FORMATS = ["%m/%d/%Y %I:%M %p", "%m/%d/%Y", "%b %d, %Y %I:%M:%S %p", "%b %d, %Y"]


def parse_lead_date(raw: str | None):
    if not raw or raw.strip().lower() == "test":
        return None
    s = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ---- sheet reading (blocking; wrapped in to_thread) ---------------------------


# read-write scope so we can stamp synced rows back; reads still work with it
_SHEET_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _sheets_client():
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(get_settings().service_account_info, scopes=_SHEET_SCOPES)
    return gspread.authorize(creds)


def _fetch_worksheet(name: str) -> list[dict]:
    ws = _sheets_client().open_by_key(get_settings().LEADS_SHEET_ID).worksheet(name)
    values = ws.get_all_values()
    if not values:
        return []
    headers = [_norm_header(h) for h in values[0]]
    rows = []
    for sheet_row, r in enumerate(values[1:], start=2):  # 1-based; row 1 = header
        if not any(c.strip() for c in r):
            continue
        row = {headers[i]: (r[i].strip() if i < len(r) else "") for i in range(len(headers))}
        row["_row"] = sheet_row  # carries the sheet row number for write-back
        rows.append(row)
    return rows


def _mark_synced(name: str, valid_rows: list[int]) -> int:
    """Stamp the configured 'synced' column with an IST timestamp on each synced sheet
    row that isn't already stamped. Adds the column header if missing. One write call."""
    import gspread

    if not valid_rows:
        return 0
    settings = get_settings()
    header_label = settings.LEADS_WRITEBACK_COLUMN
    col_key = _norm_header(header_label)
    ws = _sheets_client().open_by_key(settings.LEADS_SHEET_ID).worksheet(name)
    values = ws.get_all_values()
    if not values:
        return 0
    header = [_norm_header(h) for h in values[0]]
    if col_key in header:
        col_idx = header.index(col_key) + 1  # 1-based
    else:
        col_idx = len(values[0]) + 1
        ws.update_cell(1, col_idx, header_label)  # add the header
    ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    ts = ist.strftime("%Y-%m-%d %H:%M") + " IST"
    cells = []
    for rownum in valid_rows:
        idx = rownum - 1
        cur = values[idx][col_idx - 1] if idx < len(values) and col_idx - 1 < len(values[idx]) else ""
        if not str(cur).strip():  # only stamp rows not already marked
            cells.append(gspread.Cell(rownum, col_idx, ts))
    if cells:
        ws.update_cells(cells)
    return len(cells)


# ---- row -> table dicts -------------------------------------------------------


def build_meta(rows: list[dict]) -> tuple[list[dict], list[dict], list[int]]:
    """Returns (meta_leads rows, leads spine rows, synced sheet-row numbers). Skips no-phone rows."""
    ingest, spine, synced = [], [], []
    for r in rows:
        row_num = r.pop("_row", None)
        phone = norm_phone(r.get("phone_number"))
        if not phone:
            continue
        if row_num:
            synced.append(row_num)
        name = clean_name(r.get("full_name"))
        city = normalize_city(r.get("city"))  # Meta sheet gained a city column
        society = r.get("society") or None    # Meta sheet gained a society column
        budget = pretty_enum(r.get("your_budget_range"))
        plan = map_plan(r.get("when_are_you_planning_to_buy"))
        visit_day = pretty_enum(r.get("preferred_site_visit_day"))
        email = r.get("email") or None
        ingest.append({
            "dedupe_key": phone, "full_name": name, "phone": display_phone(phone), "email": email,
            "city": city, "society": society, "budget_range": budget, "plan_to_buy": plan,
            "preferred_visit_day": visit_day, "is_test": False, "raw": r,
        })
        spine.append({
            "origin_key": f"meta:{phone}", "source_category": "meta", "source": "meta",
            "name": name, "phone": display_phone(phone), "email": email, "assigned_to": None,
            "city": city, "society": society, "configuration": None, "budget_band": budget,
            "plan_to_buy": plan, "preferred_visit_day": visit_day, "source_remarks": None, "is_test": False,
            "received_at": None,  # meta sheet has no date → filled with ingest time below
            "source_meta": {"budget_range": budget, "plan_to_buy": plan, "preferred_visit_day": visit_day, "city": city, "society": society},
        })
    return ingest, spine, synced


def build_listing(rows: list[dict]) -> tuple[list[dict], list[dict], list[int]]:
    ingest, spine, synced = [], [], []
    for r in rows:
        row_num = r.pop("_row", None)
        phone = norm_phone(r.get("contactno"))
        name = clean_name(r.get("name"))
        if not phone or not name:
            continue
        if row_num:
            synced.append(row_num)
        source = map_source(r.get("source"))
        city = normalize_city(r.get("city"))
        prop = r.get("property") or None
        ltype = r.get("type") or None
        assigned = r.get("assigned_to") or None
        email = r.get("email_id") or None
        remarks = " | ".join(x for x in [r.get("remarks"), r.get("remarks_2")] if x) or None
        ingest.append({
            "dedupe_key": phone, "name": name, "phone": display_phone(phone), "email": email,
            "source": source, "city": city, "property": prop, "lead_type": ltype,
            "phone_verification_status": r.get("phoneverificationstatus") or None,
            "assigned_to": assigned, "lead_date": r.get("date") or None, "remarks": remarks,
            "is_test": False, "raw": r,
        })
        spine.append({
            "origin_key": f"listing:{phone}", "source_category": "listing", "source": source,
            "name": name, "phone": display_phone(phone), "email": email, "assigned_to": assigned,
            "city": city, "society": prop, "configuration": None, "budget_band": None,
            "plan_to_buy": None, "preferred_visit_day": None, "source_remarks": remarks, "is_test": False,
            "received_at": parse_lead_date(r.get("date")),
            "source_meta": {"property": prop, "lead_type": ltype, "source": source},
        })
    return ingest, spine, synced


# ---- the two test leads (idempotent via fixed dedupe_key) ---------------------

TEST_META = {
    "ingest": {"dedupe_key": "0000000001", "full_name": "TEST Meta Lead", "phone": "+91 00000 00001",
               "email": "test.meta@openhouse.in", "city": "Gurgaon", "society": "Signature Global City 93 (test)",
               "budget_range": "Up to ₹75 lacs", "plan_to_buy": "Within 30 days",
               "preferred_visit_day": "This Sunday", "is_test": True, "raw": {"_test": "true"}},
    "spine": {"origin_key": "meta:0000000001", "source_category": "meta", "source": "meta",
              "name": "TEST Meta Lead", "phone": "+91 00000 00001", "email": "test.meta@openhouse.in",
              "assigned_to": "RM 1", "city": "Gurgaon", "society": "Signature Global City 93 (test)",
              "configuration": None, "budget_band": "Up to ₹75 lacs", "plan_to_buy": "Within 30 days",
              "preferred_visit_day": "This Sunday", "source_remarks": None, "is_test": True,
              "source_meta": {"budget_range": "Up to ₹75 lacs", "plan_to_buy": "Within 30 days"}},
}
TEST_LISTING = {
    "ingest": {"dedupe_key": "0000000002", "name": "TEST Listing Lead", "phone": "+91 00000 00002",
               "email": "test.listing@openhouse.in", "source": "99acres", "city": "Noida",
               "property": "ATS Picturesque, Sec 152", "lead_type": "Individual",
               "phone_verification_status": "VERIFIED", "assigned_to": "RM 2",
               "lead_date": "test", "remarks": "Seeded test lead", "is_test": True, "raw": {"_test": "true"}},
    "spine": {"origin_key": "listing:0000000002", "source_category": "listing", "source": "99acres",
              "name": "TEST Listing Lead", "phone": "+91 00000 00002", "email": "test.listing@openhouse.in",
              "assigned_to": "RM 2", "city": "Noida", "society": "ATS Picturesque, Sec 152",
              "configuration": None, "budget_band": None, "plan_to_buy": None, "preferred_visit_day": None,
              "source_remarks": "Seeded test lead", "is_test": True,
              "source_meta": {"property": "ATS Picturesque, Sec 152", "source": "99acres"}},
}


# ---- sync core ----------------------------------------------------------------


# Postgres' wire protocol allows at most 32767 bind parameters in one statement, and
# a multi-row INSERT spends one per column per row. Exceed it and asyncpg raises
# InterfaceError before the query is even sent — which is what a full sheet of leads
# (2000+ rows) did. Leave headroom below the hard cap so an off-by-a-column never bites.
PARAM_LIMIT = 30000


def _cols_per_row(model, rows: list[dict]) -> int:
    """Bind-params SQLAlchemy emits per row = the row's own keys PLUS every column with a
    client-side default (e.g. `id = uuid.uuid4`) that the row omits — SQLAlchemy fills and
    BINDS those. Counting only dict keys undercounts by exactly those columns, which is how
    a 'chunked' insert still blew the cap (18 dict keys but 19 bound columns per lead)."""
    keys = set().union(*(r.keys() for r in rows)) if rows else set()
    auto = sum(1 for c in model.__table__.columns if c.name not in keys and c.default is not None)
    return max(1, len(keys) + auto)


async def _insert_only(conn, model, rows: list[dict], conflict_col: str) -> int:
    """Bulk INSERT ... ON CONFLICT DO NOTHING. Returns count of rows that landed.
    Chunked to stay under the bind-parameter cap; the caller's transaction spans every
    chunk, so a failure part-way still rolls the whole sync back."""
    if not rows:
        return 0
    size = max(1, PARAM_LIMIT // _cols_per_row(model, rows))
    total = 0
    for i in range(0, len(rows), size):
        stmt = (pg_insert(model).values(rows[i:i + size])
                .on_conflict_do_nothing(index_elements=[conflict_col]))
        total += (await conn.execute(stmt)).rowcount or 0
    return total


async def run_leads_sync(trigger: str = "manual") -> dict:
    """Insert-only ingest of both worksheets + spine + test leads. Never raises."""
    settings = get_settings()
    engine = neon_engine()
    if engine is None or not settings.leads_sheet_configured:
        detail = "Leads sync not configured (need DATABASE_URL + service account + LEADS_SHEET_ID)"
        await _write_state(LISTING_KEY, "not_configured", detail, None)
        await _write_state(META_KEY, "not_configured", detail, None)
        return {"status": "not_configured", "detail": detail}
    try:
        listing_rows, meta_rows = await asyncio.gather(
            asyncio.to_thread(_fetch_worksheet, settings.LEADS_LISTING_WORKSHEET),
            asyncio.to_thread(_fetch_worksheet, settings.LEADS_META_WORKSHEET),
        )
        meta_ingest, meta_spine, meta_synced = build_meta(meta_rows)
        listing_ingest, listing_spine, listing_synced = build_listing(listing_rows)

        # seed the two test leads (idempotent)
        meta_ingest.insert(0, TEST_META["ingest"])
        meta_spine.insert(0, TEST_META["spine"])
        listing_ingest.insert(0, TEST_LISTING["ingest"])
        listing_spine.insert(0, TEST_LISTING["spine"])

        now = datetime.now(timezone.utc)
        tat = now + timedelta(hours=TAT_HOURS)
        for s in (*meta_spine, *listing_spine):
            s.setdefault("tat_deadline", tat)
            if s.get("received_at") is None:  # meta + test leads → use ingest time
                s["received_at"] = now

        # backfill city onto already-ingested meta leads (insert-only never updates
        # existing spine rows; the Meta sheet gained a city column after launch)
        meta_city_updates = [
            {"ok": s["origin_key"], "city": s["city"]} for s in meta_spine if s.get("city")
        ]

        async with engine.begin() as conn:
            # resolve each lead's owner to the user's canonical full name before insert,
            # so sheet first-names and app full-names don't split one person into two
            # owners (existing rows are healed by the same map in run_migrations)
            urows = await conn.execute(text(
                "SELECT name, assignment_name FROM users WHERE active AND name IS NOT NULL"))
            canon = build_assignee_canon_map([dict(r) for r in urows.mappings()])
            for s in (*meta_spine, *listing_spine):
                if s.get("assigned_to"):
                    s["assigned_to"] = canonical_assignee(s["assigned_to"], canon)

            m_new = await _insert_only(conn, MetaLead, meta_ingest, "dedupe_key")
            l_new = await _insert_only(conn, ListingLead, listing_ingest, "dedupe_key")
            spine_new = await _insert_only(conn, Lead, [*meta_spine, *listing_spine], "origin_key")
            if meta_city_updates:
                await conn.execute(
                    text("UPDATE leads SET city = :city WHERE origin_key = :ok AND (city IS NULL OR city = '')"),
                    meta_city_updates,
                )

        await _write_state(META_KEY, "ok", f"{m_new} new via {trigger}", m_new)
        await _write_state(LISTING_KEY, "ok", f"{l_new} new via {trigger}", l_new)
        log.info("leads sync ok (%s): meta +%d, listing +%d, spine +%d", trigger, m_new, l_new, spine_new)

        # stamp the source sheet so the team sees which rows we've captured (fail-soft:
        # a write-back failure must not fail the sync — usually means no Editor access)
        if settings.LEADS_SYNC_WRITEBACK:
            try:
                m_mark, l_mark = await asyncio.gather(
                    asyncio.to_thread(_mark_synced, settings.LEADS_META_WORKSHEET, meta_synced),
                    asyncio.to_thread(_mark_synced, settings.LEADS_LISTING_WORKSHEET, listing_synced),
                )
                log.info("sheet write-back: stamped meta %d, listing %d rows", m_mark, l_mark)
            except Exception:
                log.warning(
                    "sheet write-back failed — grant Editor access to %s",
                    (settings.service_account_info or {}).get("client_email", "the service account"),
                    exc_info=True,
                )
        return {"status": "ok", "meta_new": m_new, "listing_new": l_new, "spine_new": spine_new}
    except Exception as e:  # noqa: BLE001 — sync must never crash the app
        log.exception("leads sync failed (%s)", trigger)
        await _write_state(META_KEY, "error", str(e), None)
        await _write_state(LISTING_KEY, "error", str(e), None)
        return {"status": "error", "detail": str(e)}


async def read_leads_state(conn=None) -> dict:
    """Last-sync banner data. Pass an open connection to avoid a second pool
    checkout — callers that already hold one (the leads list) should always do so."""
    engine = neon_engine()
    if engine is None and conn is None:
        return {"listing": None, "meta": None}
    try:
        async def _read(c):
            res = await c.execute(
                text("SELECT key, last_synced_at, last_status, detail, row_count FROM sync_state WHERE key IN (:a, :b)"),
                {"a": LISTING_KEY, "b": META_KEY},
            )
            out = {}
            for row in res.mappings():
                out[row["key"]] = {
                    "last_synced_at": row["last_synced_at"].isoformat() if row["last_synced_at"] else None,
                    "last_status": row["last_status"], "detail": row["detail"], "row_count": row["row_count"],
                }
            return {"listing": out.get(LISTING_KEY), "meta": out.get(META_KEY)}

        if conn is not None:
            return await _read(conn)
        async with engine.connect() as c:
            return await _read(c)
    except Exception as e:  # noqa: BLE001
        return {"listing": None, "meta": None, "error": str(e)}
