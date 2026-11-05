"""The listing flow — check, post, mark — with every DB and 99acres call faked.

The no-repeat guarantee lives in the SQL (one row per uid, claimed atomically), so the
claim's text is asserted directly; the flow tests pin the ORDER of a post, which is what
makes a crash or a timeout leave the right state behind."""
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app.services import acres_client, acres_listings
from tests.test_acres_payload import SOC, _prop

ADMIN = {"email": "a@x", "name": "A", "role": "admin"}


def _book(uid, **over):
    return _prop(**{"uid": uid, "availability_status": "Available", **over})


class _Result:
    def __init__(self, rows, rowcount=1):
        self._rows = rows
        self.rowcount = rowcount

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return next(iter(self._rows[0].values())) if self._rows else None

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


def _stub_flow(monkeypatch, *, book, listings=None, token=None, listing=None,
               claim_returns="row", current_status=None, mark_raises=None, settle_rowcount=1):
    calls = SimpleNamespace(order=[], listing_posts=0, params={}, photo_queries=0)
    listings = listings or {}

    class Conn:
        async def execute(self, stmt, params=None):
            name = next((n for n in ("CLAIM_SQL", "SETTLE_SQL", "NOTE_SQL", "CURRENT_SQL", "STATUSES_SQL",
                                     "MARK_LIVE_SQL", "MARK_SQL") if stmt is getattr(acres_listings, n)), None)
            calls.params[name] = params
            if name == "CLAIM_SQL":
                calls.order.append("claim")
                return _Result([{"uid": params["uid"]}] if claim_returns else [])
            if name == "SETTLE_SQL":
                calls.order.append("settle")
                return _Result([], settle_rowcount)
            if name == "CURRENT_SQL":
                return _Result([{"status": current_status}])
            if name == "STATUSES_SQL":
                return _Result([{"uid": u, "status": s} for u, s in listings.items()])
            if name in ("MARK_LIVE_SQL", "MARK_SQL"):
                if mark_raises:
                    raise mark_raises
                return _Result([{"uid": params["uid"], "status": params.get("to", "live"),
                                 "prop_id": params.get("prop_id"), "before": None}])
            return _Result([])

    class Ctx:
        def __init__(self, commits):
            self.commits = commits

        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, exc_type, *_):
            if self.commits and exc_type is None:
                calls.order.append("commit")

    engine = SimpleNamespace(begin=lambda: Ctx(True), connect=lambda: Ctx(False))

    async def fake_token(force=False):
        calls.order.append("token")
        if token:
            raise token
        return "t"

    async def fake_call(method, path, body=None):
        calls.order.append("listing")
        calls.listing_posts += 1
        if listing:
            raise listing
        return {"status": True, "prop_id": "E1", "quality_score": 70}

    async def fake_props():
        return {"status": "ok", "items": book}

    async def fake_photos(uids):
        calls.photo_queries += 1
        return {}

    async def fake_facts():
        return {p["society_name"].strip().lower(): SOC for p in book}

    monkeypatch.setattr(acres_listings, "neon_engine", lambda: engine)
    monkeypatch.setattr(acres_listings, "fetch_properties", fake_props)
    monkeypatch.setattr(acres_listings, "studio_photos", fake_photos)
    monkeypatch.setattr(acres_listings, "society_facts", fake_facts)
    monkeypatch.setattr(acres_client, "token", fake_token)
    monkeypatch.setattr(acres_client, "call", fake_call)
    return calls


def test_claim_only_takes_new_failed_or_removed_rows():               # Review Focus 1
    sql = " ".join(acres_listings.CLAIM_SQL.text.split())
    assert "ON CONFLICT (uid) DO UPDATE" in sql and "WHERE acres_listings.status IN ('failed', 'removed')" in sql
    assert "'unknown'" in sql and "RETURNING" in sql


async def test_a_request_repeating_a_uid_posts_it_once(monkeypatch):  # Review Focus 1
    calls = _stub_flow(monkeypatch, book=[_book("OHND1166")])
    out = await acres_listings.post([{"uid": "OHND1166", "owntype": "2"}] * 2, photos=False, user=ADMIN)
    assert len(out) == 1 and calls.listing_posts == 1


async def test_unknown_is_committed_before_99acres_is_called(monkeypatch):
    calls = _stub_flow(monkeypatch, book=[_book("U1")])
    [r] = await acres_listings.post([{"uid": "U1", "owntype": "2"}], photos=False, user=ADMIN)
    assert calls.order == ["token", "claim", "commit", "listing", "settle", "commit"]
    assert (r["status"], r["prop_id"], r["quality_score"]) == ("live", "E1", 70)
    assert calls.params["SETTLE_SQL"]["status"] == "live" and calls.params["CLAIM_SQL"]["age"] == "2"


async def test_a_timeout_leaves_the_row_unknown(monkeypatch):
    calls = _stub_flow(monkeypatch, book=[_book("U1")], listing=httpx.ReadTimeout("slow"))
    [r] = await acres_listings.post([{"uid": "U1", "owntype": "2"}], photos=False, user=ADMIN)
    assert r["status"] == "unknown" and "check its dashboard" in r["error"] and "settle" not in calls.order


async def test_an_edge_block_is_failed_not_unknown(monkeypatch):
    calls = _stub_flow(monkeypatch, book=[_book("U1")], listing=acres_client.AcresError("Blocked by 99acres' firewall (Akamai 403) — nothing was created"))
    [r] = await acres_listings.post([{"uid": "U1", "owntype": "2"}], photos=False, user=ADMIN)
    assert r["status"] == "failed" and calls.params["SETTLE_SQL"]["status"] == "failed"


async def test_a_login_failure_claims_nothing(monkeypatch):
    calls = _stub_flow(monkeypatch, book=[_book("U1")], token=acres_client.AcresError("99acres refused our IP"))
    with pytest.raises(acres_client.AcresError):
        await acres_listings.post([{"uid": "U1", "owntype": "2"}], photos=False, user=ADMIN)
    assert "claim" not in calls.order


async def test_post_refuses_a_property_that_is_no_longer_available(monkeypatch):   # Review Focus 2
    calls = _stub_flow(monkeypatch, book=[_book("U1", availability_status="Sold")])
    [r] = await acres_listings.post([{"uid": "U1", "owntype": "2"}], photos=False, user=ADMIN)
    assert r["error"] == "Not Available (Sold) — not posted" and "claim" not in calls.order


async def test_problems_are_returned_and_nothing_is_claimed(monkeypatch):
    calls = _stub_flow(monkeypatch, book=[_book("U1")])
    [r] = await acres_listings.post([{"uid": "U1", "owntype": None}], photos=False, user=ADMIN)
    assert r["problems"] == ["Ownership not set"] and "claim" not in calls.order


async def test_a_refused_claim_reports_the_current_status(monkeypatch):
    calls = _stub_flow(monkeypatch, book=[_book("U1")], claim_returns=None, current_status="live")
    [r] = await acres_listings.post([{"uid": "U1", "owntype": "2"}], photos=False, user=ADMIN)
    assert r["error"] == "Already live on 99acres" and calls.listing_posts == 0


async def test_check_flags_lookalikes_and_never_calls_99acres(monkeypatch):
    calls = _stub_flow(monkeypatch, book=[_book("A"), _book("B"), _book("C", area_sqft=999.0)], listings={"B": "live"})
    out = {r["uid"]: r for r in await acres_listings.check([{"uid": "A", "owntype": "2"}], photos=True)}
    assert out["A"]["lookalikes"] == [{"uid": "B", "status": "live"}] and out["A"]["ok"] is True
    assert out["A"]["age"] == "2" and out["A"]["pin"] == {"lat": 28.57, "lng": 77.38}
    assert "listing" not in calls.order and "token" not in calls.order


async def test_check_marks_a_live_property_not_ok(monkeypatch):
    _stub_flow(monkeypatch, book=[_book("A")], listings={"A": "live"})
    [r] = await acres_listings.check([{"uid": "A", "owntype": "2"}], photos=False)
    assert r["ok"] is False and r["status"] == "live" and r["problems"] == []


def test_hand_transitions():
    assert acres_listings.MARK_FROM == {"live": (None, "failed", "duplicate", "unknown"),
                                        "failed": ("unknown", "duplicate"), "removed": ("live",)}
    assert "ON CONFLICT (uid) DO UPDATE" in acres_listings.MARK_LIVE_SQL.text
    assert "INSERT" not in acres_listings.MARK_SQL.text          # only "live" may create a row


async def test_marking_live_needs_a_listing_id(monkeypatch):
    _stub_flow(monkeypatch, book=[])
    with pytest.raises(ValueError, match="listing id"):
        await acres_listings.mark("U1", "live", None, ADMIN)


async def test_a_listing_id_already_on_another_property_is_refused(monkeypatch):
    _stub_flow(monkeypatch, book=[], mark_raises=IntegrityError("stmt", {}, Exception("duplicate key prop_id")))
    with pytest.raises(ValueError, match="already recorded on another property"):
        await acres_listings.mark("OHNC1882", "live", "P95503744", ADMIN)


def test_society_facts_only_selects_columns_that_exist():
    sql = acres_listings.society_facts_sql({"society_name", "latitude"})
    assert "latitude" in sql and "possession_year" not in sql and "INSERT" not in sql.upper()
    assert "LOWER(TRIM(society_name))" in sql


async def test_photos_are_fetched_in_one_query_per_request(monkeypatch):
    """One studio query per request, never one per property: N+1 against the Singapore DB
    turned 253 lookups into five minutes."""
    calls = _stub_flow(monkeypatch, book=[_book("A"), _book("B"), _book("C")])
    await acres_listings.check([{"uid": u, "owntype": "2"} for u in "ABC"], photos=True)
    assert calls.photo_queries == 1
    calls.photo_queries = 0
    await acres_listings.check([{"uid": u, "owntype": "2"} for u in "ABC"], photos=False)
    assert calls.photo_queries == 0


async def test_a_run_halts_after_an_unknown(monkeypatch):
    """One lost answer must not become N rows to clear by hand (final review)."""
    calls = _stub_flow(monkeypatch, book=[_book("U1"), _book("U2"), _book("U3")], listing=httpx.ReadTimeout("slow"))
    out = await acres_listings.post([{"uid": u, "owntype": "2"} for u in ("U1", "U2", "U3")], photos=False, user=ADMIN)
    assert [r["status"] for r in out] == ["unknown", None, None] and out[0]["halt"] is True
    assert out[1]["error"] == "Not attempted — the run stopped" and calls.order.count("claim") == 1


async def test_a_run_halts_after_an_edge_or_ip_refusal(monkeypatch):
    calls = _stub_flow(monkeypatch, book=[_book("U1"), _book("U2")], listing=acres_client.AcresError("Blocked by 99acres' firewall (Akamai 403) — nothing was created"))
    out = await acres_listings.post([{"uid": u, "owntype": "2"} for u in ("U1", "U2")], photos=False, user=ADMIN)
    assert out[0]["status"] == "failed" and out[0]["halt"] is True and calls.listing_posts == 1


def test_a_live_answer_lands_even_if_the_row_was_marked_failed_meanwhile():
    """An admin may mark an in-flight 'unknown' as failed; the live answer must still attach its
    prop_id, or the table says postable while 99acres has the listing."""
    sql = " ".join(acres_listings.SETTLE_SQL.text.split())
    assert "status = 'unknown' OR (CAST(:status AS text) = 'live' AND status = 'failed')" in sql


async def test_a_settle_that_finds_no_row_says_so(monkeypatch):
    _stub_flow(monkeypatch, book=[_book("U1")], settle_rowcount=0)
    [r] = await acres_listings.post([{"uid": "U1", "owntype": "2"}], photos=False, user=ADMIN)
    assert r["status"] == "live" and "record changed" in r["error"]


def test_a_recent_unknown_cannot_be_marked_not_on_99acres():
    """A claim younger than five minutes may still be in flight (call timeout + queue)."""
    sql = " ".join(acres_listings.MARK_SQL.text.split())
    assert "NOT (status = 'unknown' AND updated_at > now() - interval '5 minutes')" in sql
