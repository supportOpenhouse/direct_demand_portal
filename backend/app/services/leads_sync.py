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
from ..db import neon_engine
from ..models import Lead, ListingLead, MetaLead, SyncState

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


# ---- sheet reading (blocking; wrapped in to_thread) ---------------------------


def _fetch_worksheet(name: str) -> list[dict]:
    import gspread
    from google.oauth2.service_account import Credentials

    settings = get_settings()
    creds = Credentials.from_service_account_info(
        settings.service_account_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    client = gspread.authorize(creds)
    ws = client.open_by_key(settings.LEADS_SHEET_ID).worksheet(name)
    values = ws.get_all_values()
    if not values:
        return []
    headers = [_norm_header(h) for h in values[0]]
    rows = []
    for r in values[1:]:
        if not any(c.strip() for c in r):
            continue
        rows.append({headers[i]: (r[i].strip() if i < len(r) else "") for i in range(len(headers))})
    return rows


# ---- row -> table dicts -------------------------------------------------------


def build_meta(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Returns (meta_leads rows, leads spine rows). Skips rows with no phone."""
    ingest, spine = [], []
    for r in rows:
        phone = norm_phone(r.get("phone_number"))
        if not phone:
            continue
        name = clean_name(r.get("full_name"))
        budget = pretty_enum(r.get("your_budget_range"))
        plan = map_plan(r.get("when_are_you_planning_to_buy"))
        visit_day = pretty_enum(r.get("preferred_site_visit_day"))
        email = r.get("email") or None
        ingest.append({
            "dedupe_key": phone, "full_name": name, "phone": display_phone(phone), "email": email,
            "budget_range": budget, "plan_to_buy": plan, "preferred_visit_day": visit_day,
            "is_test": False, "raw": r,
        })
        spine.append({
            "origin_key": f"meta:{phone}", "source_category": "meta", "source": "meta",
            "name": name, "phone": display_phone(phone), "email": email, "assigned_to": None,
            "city": None, "society": None, "configuration": None, "budget_band": budget,
            "plan_to_buy": plan, "preferred_visit_day": visit_day, "source_remarks": None, "is_test": False,
            "source_meta": {"budget_range": budget, "plan_to_buy": plan, "preferred_visit_day": visit_day},
        })
    return ingest, spine


def build_listing(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    ingest, spine = [], []
    for r in rows:
        phone = norm_phone(r.get("contactno"))
        name = clean_name(r.get("name"))
        if not phone or not name:
            continue
        source = map_source(r.get("source"))
        city = r.get("city") or None
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
            "source_meta": {"property": prop, "lead_type": ltype, "source": source},
        })
    return ingest, spine


# ---- the two test leads (idempotent via fixed dedupe_key) ---------------------

TEST_META = {
    "ingest": {"dedupe_key": "0000000001", "full_name": "TEST Meta Lead", "phone": "+91 00000 00001",
               "email": "test.meta@openhouse.in", "budget_range": "Up to ₹75 lacs",
               "plan_to_buy": "Within 30 days", "preferred_visit_day": "This Sunday", "is_test": True,
               "raw": {"_test": "true"}},
    "spine": {"origin_key": "meta:0000000001", "source_category": "meta", "source": "meta",
              "name": "TEST Meta Lead", "phone": "+91 00000 00001", "email": "test.meta@openhouse.in",
              "assigned_to": "RM 1", "city": "Gurgaon", "society": None, "configuration": None,
              "budget_band": "Up to ₹75 lacs", "plan_to_buy": "Within 30 days",
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


async def _insert_only(conn, model, rows: list[dict], conflict_col: str) -> int:
    """Bulk INSERT ... ON CONFLICT DO NOTHING. Returns count of rows that landed."""
    if not rows:
        return 0
    stmt = pg_insert(model).values(rows).on_conflict_do_nothing(index_elements=[conflict_col])
    result = await conn.execute(stmt)
    return result.rowcount or 0


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
        meta_ingest, meta_spine = build_meta(meta_rows)
        listing_ingest, listing_spine = build_listing(listing_rows)

        # seed the two test leads (idempotent)
        meta_ingest.insert(0, TEST_META["ingest"]); meta_spine.insert(0, TEST_META["spine"])
        listing_ingest.insert(0, TEST_LISTING["ingest"]); listing_spine.insert(0, TEST_LISTING["spine"])

        tat = datetime.now(timezone.utc) + timedelta(hours=TAT_HOURS)
        for s in (*meta_spine, *listing_spine):
            s.setdefault("tat_deadline", tat)

        async with engine.begin() as conn:
            m_new = await _insert_only(conn, MetaLead, meta_ingest, "dedupe_key")
            l_new = await _insert_only(conn, ListingLead, listing_ingest, "dedupe_key")
            spine_new = await _insert_only(conn, Lead, [*meta_spine, *listing_spine], "origin_key")

        await _write_state(META_KEY, "ok", f"{m_new} new via {trigger}", m_new)
        await _write_state(LISTING_KEY, "ok", f"{l_new} new via {trigger}", l_new)
        log.info("leads sync ok (%s): meta +%d, listing +%d, spine +%d", trigger, m_new, l_new, spine_new)
        return {"status": "ok", "meta_new": m_new, "listing_new": l_new, "spine_new": spine_new}
    except Exception as e:  # noqa: BLE001 — sync must never crash the app
        log.exception("leads sync failed (%s)", trigger)
        await _write_state(META_KEY, "error", str(e), None)
        await _write_state(LISTING_KEY, "error", str(e), None)
        return {"status": "error", "detail": str(e)}


async def read_leads_state() -> dict:
    engine = neon_engine()
    if engine is None:
        return {"listing": None, "meta": None}
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
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
    except Exception as e:  # noqa: BLE001
        return {"listing": None, "meta": None, "error": str(e)}
