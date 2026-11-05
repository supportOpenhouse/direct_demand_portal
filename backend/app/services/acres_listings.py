"""Listing Demand Dashboard properties on 99acres: check, post, and the hand transitions.

Spec: docs/superpowers/specs/2026-11-05-99acres-listing-design.md.

THE NO-REPEAT GUARANTEE is `acres_listings` (our Neon DB): one row per property uid, a
unique 99acres prop_id, and a claim that is one atomic statement — it only takes a property
that has no row, or whose last attempt `failed` / was `removed`. Two admins, a double click
or overlapping runs cannot both get it.

Statuses:
  unknown   claimed and sent; 99acres' answer not recorded. It MAY exist on 99acres, so it is
            never re-posted until an admin checks and resolves it by hand.
  live      has a prop_id — we posted it, or an admin recorded one posted by hand
  failed    99acres refused it; nothing was created; postable again
  duplicate 99acres said errorCode 5 "similar to …"; an admin may set it back to failed
  removed   an admin took it down by hand on 99acres (the API delete is blocked)

The order of a post is load-bearing: log in → claim (own COMMITTED transaction, status
`unknown`) → call 99acres → record the answer. A crash between the last two leaves exactly
`unknown`, which is the truth.
"""
import json
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..db import neon_engine, properties_engine, studio_engine
from . import acres_client
from .acres_payload import build_payload, lookalike_key
from .activity import Actor, record, row_for
from .demand_dashboard import fetch_properties

CLAIMABLE = (None, "failed", "removed")
LOOKALIKE_STATUSES = ("live", "unknown", "duplicate")
NO_ANSWER = "No answer from 99acres — check its dashboard before retrying"
NOT_ATTEMPTED = "Not attempted — the run stopped"
MARK_FROM: dict[str, tuple[str | None, ...]] = {
    "live": (None, "failed", "duplicate", "unknown"),   # recorded by hand (needs a prop_id)
    "failed": ("unknown", "duplicate"),                 # "Not on 99acres" / "Try again"
    "removed": ("live",),                               # taken down by hand on 99acres
}

LIST_SQL = text("""
    SELECT uid, status, prop_id, source, age, owntype, error, quality_score,
           posted_at, updated_at, updated_by
      FROM acres_listings ORDER BY updated_at DESC
""")
STATUSES_SQL = text("SELECT uid, status FROM acres_listings")
CURRENT_SQL = text("SELECT status FROM acres_listings WHERE uid = :uid")

CLAIM_SQL = text("""
    INSERT INTO acres_listings (uid, status, source, age, owntype, payload, updated_at, updated_by)
    VALUES (:uid, 'unknown', 'api', :age, :owntype, CAST(:payload AS jsonb), now(), :by)
    ON CONFLICT (uid) DO UPDATE
       SET status = 'unknown', source = 'api', age = EXCLUDED.age, owntype = EXCLUDED.owntype,
           payload = EXCLUDED.payload, response = NULL, error = NULL, prop_id = NULL,
           quality_score = NULL, updated_at = now(), updated_by = EXCLUDED.updated_by
     WHERE acres_listings.status IN ('failed', 'removed')
    RETURNING uid
""")

SETTLE_SQL = text("""
    UPDATE acres_listings
       SET status = CAST(:status AS text), prop_id = :prop_id, quality_score = :quality_score,
           response = CAST(:response AS jsonb), error = :error, updated_at = now(),
           posted_at = CASE WHEN CAST(:status AS text) = 'live' THEN now() ELSE posted_at END
     WHERE uid = :uid
       AND (status = 'unknown' OR (CAST(:status AS text) = 'live' AND status = 'failed'))
""")
# ↑ An admin may mark an in-flight claim "Not on 99acres" (failed); a live answer must still
#   attach its prop_id, or the table says postable while 99acres holds the listing.

# The outcome is unknown: keep the claim, note why.
NOTE_SQL = text("""
    UPDATE acres_listings SET error = :error, response = CAST(:response AS jsonb), updated_at = now()
     WHERE uid = :uid AND status = 'unknown'
""")

# Hand transitions. `before` comes from the pre-statement snapshot, never a second SELECT.
MARK_LIVE_SQL = text("""
    INSERT INTO acres_listings (uid, status, prop_id, source, updated_at, updated_by)
    VALUES (:uid, 'live', :prop_id, 'manual', now(), :by)
    ON CONFLICT (uid) DO UPDATE
       SET status = 'live', prop_id = EXCLUDED.prop_id, error = NULL,
           source = CASE WHEN acres_listings.status = 'unknown' THEN acres_listings.source ELSE 'manual' END,
           posted_at = CASE WHEN acres_listings.status = 'unknown' THEN now() ELSE acres_listings.posted_at END,
           updated_at = now(), updated_by = EXCLUDED.updated_by
     WHERE acres_listings.status IN ('failed', 'duplicate', 'unknown')
    RETURNING uid, status, prop_id, (SELECT status FROM acres_listings WHERE uid = :uid) AS before
""")
MARK_SQL = text("""
    UPDATE acres_listings SET status = :to, updated_at = now(), updated_by = :by
     WHERE uid = :uid AND status = ANY(CAST(:from AS text[]))
       -- a claim this young may still be in flight (60 s call timeout + the one-at-a-time queue)
       AND NOT (status = 'unknown' AND updated_at > now() - interval '5 minutes')
    RETURNING uid, status, prop_id, (SELECT status FROM acres_listings WHERE uid = :uid) AS before
""")

FACT_COLUMNS = ("latitude", "longitude", "possession_year")
MASTER_COLUMNS = text("""
    SELECT column_name FROM information_schema.columns WHERE table_name = 'master_societies'
""")


def society_facts_sql(columns: set[str]) -> str:
    """Only the fact columns that exist — the user adds them later, so this has to read
    the table as it is today and as it will be."""
    cols = [c for c in FACT_COLUMNS if c in columns]
    tiebreak = "latitude IS NULL, " if "latitude" in cols else ""
    return (f"SELECT DISTINCT ON (LOWER(TRIM(society_name))) "
            f"{', '.join(['LOWER(TRIM(society_name)) AS k', *cols])} "
            f"FROM master_societies WHERE society_name IS NOT NULL "
            f"ORDER BY LOWER(TRIM(society_name)), {tiebreak}id")


async def society_facts() -> dict[str, dict]:
    """master_societies (properties DB, read-only) keyed like the dashboard's own join."""
    engine = properties_engine()
    if engine is None:   # same as fetch_properties: no book, so nothing is postable anyway
        return {}
    async with engine.connect() as conn:
        cols = {r[0] for r in await conn.execute(MASTER_COLUMNS)}
        rows = (await conn.execute(text(society_facts_sql(cols)))).mappings().all()
    return {r["k"]: {c: r[c] for c in FACT_COLUMNS if c in r} for r in rows}


STUDIO_PHOTOS_SQL = text("""
    SELECT property_uid, slot_id, url FROM onboarded_properties_photos
     WHERE property_uid = ANY(CAST(:uids AS text[])) AND url LIKE 'https://%'
     ORDER BY property_uid, slot_id
""")


async def studio_photos(uids: list[str]) -> dict[str, list[dict]]:
    """Every studio photo for these properties in ONE query (Openhouse Studio DB, read-only).
    One query per property is N+1 against Singapore: 253 of them took five minutes."""
    engine = studio_engine()
    if engine is None:
        raise acres_client.AcresNotConfigured(
            "The Openhouse Studio DB isn't configured, so photos can't be sent — untick Send photos")
    out: dict[str, list[dict]] = defaultdict(list)
    async with engine.connect() as conn:
        for r in (await conn.execute(STUDIO_PHOTOS_SQL, {"uids": uids})).mappings():
            out[r["property_uid"]].append({"slot_id": r["slot_id"], "url": r["url"]})
    return out


def _ist_year() -> int:
    return datetime.now(ZoneInfo("Asia/Kolkata")).year


def _dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    return [it for it in items if not (it["uid"] in seen or seen.add(it["uid"]))]


def _society(p: dict, facts: dict[str, dict]) -> dict | None:
    return facts.get((p.get("society_name") or "").strip().lower())


async def _statuses() -> dict[str, str]:
    async with neon_engine().connect() as conn:
        return {r["uid"]: r["status"] for r in (await conn.execute(STATUSES_SQL)).mappings().all()}


async def list_listings() -> list[dict]:
    async with neon_engine().connect() as conn:
        return [dict(r) for r in (await conn.execute(LIST_SQL)).mappings().all()]


async def check(items: list[dict], *, photos: bool) -> list[dict]:
    """What a post WOULD send, and why it can't. Writes nothing; never calls 99acres."""
    items = _dedupe(items)
    book = {p["uid"]: p for p in (await fetch_properties())["items"]}
    facts = await society_facts()
    statuses = await _statuses()
    groups: dict[tuple, list[str]] = defaultdict(list)
    for p in book.values():
        if p["availability_status"] == "Available" or statuses.get(p["uid"]) in LOOKALIKE_STATUSES:
            groups[lookalike_key(p)].append(p["uid"])
    year = _ist_year()
    shots_by_uid = await studio_photos([it["uid"] for it in items if it["uid"] in book]) if photos else {}
    out = []
    for it in items:
        uid, status = it["uid"], statuses.get(it["uid"])
        p = book.get(uid)
        if p is None:
            out.append({"uid": uid, "ok": False, "problems": ["Not in the Demand Dashboard"], "status": status,
                        "age": None, "lookalikes": [], "payload": None, "pin": None})
            continue
        payload, problems = build_payload(p, photos=shots_by_uid.get(uid, []), owntype=it.get("owntype"),
                                          society=_society(p, facts), year=year)
        if p["availability_status"] != "Available":
            problems = [f"Not Available ({p['availability_status']})", *problems]
        out.append({
            "uid": uid, "ok": not problems and status in CLAIMABLE, "problems": problems,
            "status": status, "age": payload.get("Age"), "payload": payload,
            "lookalikes": [{"uid": u, "status": statuses.get(u)}
                           for u in groups.get(lookalike_key(p), []) if u != uid],
            "pin": ({"lat": float(payload["Latitude"]), "lng": float(payload["Longitude"])}
                    if "Latitude" in payload else None),
        })
    return out


async def post(items: list[dict], *, photos: bool, user: dict) -> list[dict]:
    """Post each item, in order. AcresNotConfigured / a login AcresError propagate before
    anything is claimed."""
    items = _dedupe(items)
    await acres_client.token()
    book = {p["uid"]: p for p in (await fetch_properties())["items"]}
    facts = await society_facts()
    year = _ist_year()
    shots_by_uid = await studio_photos([it["uid"] for it in items if it["uid"] in book]) if photos else {}
    engine = neon_engine()
    out = []
    for n, it in enumerate(items):
        uid = it["uid"]
        res = {"uid": uid, "status": None, "prop_id": None, "quality_score": None, "error": None,
               "problems": [], "halt": False}
        out.append(res)
        p = book.get(uid)
        if p is None:
            res["error"] = "Not in the Demand Dashboard"
            continue
        if p["availability_status"] != "Available":   # re-checked here: it may have sold since /check
            res["error"] = f"Not Available ({p['availability_status']}) — not posted"
            continue
        payload, problems = build_payload(p, photos=shots_by_uid.get(uid, []), owntype=it.get("owntype"),
                                          society=_society(p, facts), year=year)
        if problems:
            res["problems"] = problems
            continue

        async with engine.begin() as conn:
            claimed = (await conn.execute(CLAIM_SQL, {
                "uid": uid, "age": payload.get("Age"), "owntype": it.get("owntype"),
                "payload": json.dumps(payload), "by": user.get("email")})).first()
            current = None if claimed else (await conn.execute(CURRENT_SQL, {"uid": uid})).scalar()
        if not claimed:
            res |= {"status": current, "error": f"Already {current} on 99acres"}
            continue

        body = None
        try:
            body = await acres_client.call("POST", "v21/listing", payload)
            status, fields = acres_client.outcome_of(body)
        except acres_client.AcresError as e:     # refused before 99acres acted (edge, IP, proxy)
            status, fields = "failed", {"error": str(e)}
            res["halt"] = True                   # the same refusal awaits every item after it
        except (httpx.HTTPError, ValueError):    # it may or may not exist now
            status, fields = "unknown", {"error": NO_ANSWER}
        if status == "unknown":
            res["halt"] = True                   # one lost answer must not become N rows to clear
        res |= {"status": status, "error": fields.get("error"),
                "prop_id": fields.get("prop_id"), "quality_score": fields.get("quality_score")}

        async with engine.begin() as conn:
            if status == "unknown":
                await conn.execute(NOTE_SQL, {"uid": uid, "error": res["error"],
                                              "response": json.dumps(body) if body is not None else None})
            else:
                settled = await conn.execute(SETTLE_SQL, {
                    "uid": uid, "status": status, "prop_id": res["prop_id"],
                    "quality_score": res["quality_score"], "error": res["error"],
                    "response": json.dumps(body) if body is not None else None})
                if settled.rowcount == 0:   # its record was changed by hand while it posted
                    res["error"] = (f"99acres answered {status}{' ' + res['prop_id'] if res['prop_id'] else ''}, "
                                    "but its record changed meanwhile — check it")
            await record(conn, row_for(Actor.of(user), entity_type="property", entity_id=uid,
                                       action="acres_posted", metadata={
                                           "status": status, "prop_id": res["prop_id"],
                                           "quality_score": res["quality_score"], "error": res["error"],
                                           "photos": len(payload.get("PhotosData") or [])}))
        if res["halt"]:
            out += [{"uid": rest["uid"], "status": None, "prop_id": None, "quality_score": None,
                     "error": NOT_ATTEMPTED, "problems": [], "halt": False} for rest in items[n + 1:]]
            break
    return out


async def mark(uid: str, to: str, prop_id: str | None, user: dict) -> dict:
    """A hand transition: recorded live, not on 99acres / try again, removed."""
    if to not in MARK_FROM:
        raise ValueError(f"Unknown status '{to}'")
    if to == "live" and not prop_id:
        raise ValueError("A 99acres listing id is needed to record it as live")
    async with neon_engine().begin() as conn:
        try:
            if to == "live":
                row = (await conn.execute(MARK_LIVE_SQL, {"uid": uid, "prop_id": prop_id,
                                                          "by": user.get("email")})).mappings().first()
            else:
                row = (await conn.execute(MARK_SQL, {"uid": uid, "to": to, "by": user.get("email"),
                                                     "from": [s for s in MARK_FROM[to] if s]})).mappings().first()
        except IntegrityError:
            raise ValueError(f"{prop_id} is already recorded on another property")
        if not row:
            current = (await conn.execute(CURRENT_SQL, {"uid": uid})).scalar()
            raise ValueError(f"Can't mark a property that is {current or 'not listed'} as {to}"
                             + (" — it may still be posting; try again in a few minutes"
                                if current == "unknown" else ""))
        await record(conn, row_for(Actor.of(user), entity_type="property", entity_id=uid,
                                   action="acres_marked", field="status", before=row["before"],
                                   after=row["status"], metadata={"prop_id": row["prop_id"]}))
    return dict(row)
