"""Meta lead-ads webhook.

No database and no network, per the house rule: the DB-bound parts are covered by
asserting the rules their SQL encodes, and the valuable test here is the last one —
that a real Meta `field_data` payload lands on the existing sheet ingest with no
mapping code in between. That claim is the reason this integration is small, and it
breaks silently if anyone renames a key.
"""
import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException

from app.services import meta_leads
from app.services.leads_sync import build_meta, normalise_pushed

SECRET = "app-secret-abc"


class _Settings:
    """Only the fields meta_leads reads."""

    def __init__(self, *, secret="", verify="", prod=False):
        self.META_APP_SECRET = secret
        self.META_VERIFY_TOKEN = verify
        self.is_prod = prod


def _use(monkeypatch, **kwargs):
    monkeypatch.setattr(meta_leads, "get_settings", lambda: _Settings(**kwargs))


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---- signature ----------------------------------------------------------------


def test_a_correctly_signed_body_is_accepted(monkeypatch):
    _use(monkeypatch, secret=SECRET)
    body = b'{"object":"page","entry":[]}'
    meta_leads.check_signature(body, _sign(body))  # does not raise


def test_a_tampered_body_is_refused(monkeypatch):
    _use(monkeypatch, secret=SECRET)
    body = b'{"object":"page","entry":[]}'
    signature = _sign(body)
    with pytest.raises(HTTPException) as e:
        meta_leads.check_signature(body + b" ", signature)
    assert e.value.status_code == 403


def test_a_signature_from_another_secret_is_refused(monkeypatch):
    _use(monkeypatch, secret=SECRET)
    body = b"{}"
    with pytest.raises(HTTPException) as e:
        meta_leads.check_signature(body, _sign(body, "someone-elses-secret"))
    assert e.value.status_code == 403


def test_a_missing_signature_header_is_refused(monkeypatch):
    _use(monkeypatch, secret=SECRET)
    with pytest.raises(HTTPException) as e:
        meta_leads.check_signature(b"{}", None)
    assert e.value.status_code == 403


def test_production_refuses_to_run_the_webhook_unsecured(monkeypatch):
    """An unset secret in prod is a public endpoint that inserts leads."""
    _use(monkeypatch, secret="", prod=True)
    with pytest.raises(HTTPException) as e:
        meta_leads.check_signature(b"{}", None)
    assert e.value.status_code == 503


def test_an_unset_secret_is_open_in_dev(monkeypatch):
    _use(monkeypatch, secret="", prod=False)
    meta_leads.check_signature(b"{}", None)  # does not raise


# ---- handshake ----------------------------------------------------------------


def test_the_right_verify_token_passes(monkeypatch):
    _use(monkeypatch, verify="oh-dd-7c2f9a")
    meta_leads.check_verify_token("oh-dd-7c2f9a")


def test_a_wrong_verify_token_is_refused(monkeypatch):
    _use(monkeypatch, verify="oh-dd-7c2f9a")
    with pytest.raises(HTTPException) as e:
        meta_leads.check_verify_token("guess")
    assert e.value.status_code == 403


# ---- payload ------------------------------------------------------------------


def test_only_leadgen_changes_are_acted_on():
    payload = {"object": "page", "entry": [{"changes": [
        {"field": "feed", "value": {"post_id": "1"}},
        {"field": "leadgen", "value": {"leadgen_id": "L1", "form_id": "F1"}},
    ]}]}
    assert [v["leadgen_id"] for v in meta_leads.leadgen_values(payload)] == ["L1"]


def test_a_batched_delivery_yields_every_lead():
    payload = {"entry": [
        {"changes": [{"field": "leadgen", "value": {"leadgen_id": "L1"}},
                     {"field": "leadgen", "value": {"leadgen_id": "L2"}}]},
        {"changes": [{"field": "leadgen", "value": {"leadgen_id": "L3"}}]},
    ]}
    assert [v["leadgen_id"] for v in meta_leads.leadgen_values(payload)] == ["L1", "L2", "L3"]


def test_a_change_with_no_leadgen_id_is_dropped():
    """Nothing to fetch and nothing to retry, so it must not become a failed row."""
    payload = {"entry": [{"changes": [{"field": "leadgen", "value": {}}]}]}
    assert meta_leads.leadgen_values(payload) == []


def test_an_empty_payload_is_not_an_error():
    assert meta_leads.leadgen_values({}) == []


def test_flatten_takes_the_first_value_and_keeps_unanswered_keys():
    lead = {"field_data": [
        {"name": "full_name", "values": ["Rahul Sharma"]},
        {"name": "email", "values": []},
    ]}
    assert meta_leads.flatten(lead) == {"full_name": "Rahul Sharma", "email": ""}


# ---- the rules the SQL encodes ------------------------------------------------


def test_a_second_delivery_never_rewrites_a_lead_s_attribution():
    """origin_key is the lead's identity; the first leadgen_id to arrive keeps it."""
    assert "meta_lead_id IS NULL" in str(meta_leads.STAMP_LEAD)
    assert "origin_key = :origin_key" in str(meta_leads.STAMP_LEAD)


def test_the_same_delivery_twice_is_one_event_row():
    sql = str(meta_leads.UPSERT_EVENT)
    assert "ON CONFLICT (meta_lead_id)" in sql
    # the prior status has to be read from the pre-statement snapshot, not a second
    # query that would race Meta's retry of the same leadgen_id
    assert "prior_status" in sql


def test_every_processing_attempt_is_counted():
    assert "attempts = attempts + 1" in str(meta_leads.MARK_EVENT)


# ---- the claim the whole design rests on --------------------------------------


def test_a_real_meta_payload_needs_no_mapping_code():
    """Meta's own Instant Form field names are what `build_meta` already reads.

    This is why the webhook adds no transform: flatten -> normalise_pushed -> build_meta
    produces exactly the lead the 4-hourly sheet cron produces, right down to the
    origin_key that lets both run at once.
    """
    lead = {"id": "L1", "field_data": [
        {"name": "full_name", "values": ["Rahul Sharma"]},
        {"name": "phone_number", "values": ["+91 99997 99588"]},
        {"name": "email", "values": ["rahul@example.com"]},
        {"name": "zip_code", "values": ["z:201305"]},
        {"name": "your_budget_range?", "values": ["up_to_₹75_lacs"]},
        {"name": "preferred_site_visit_day?", "values": ["saturday"]},
        {"name": "where_are_you_looking_to_buy_a_home", "values": ["Noida"]},
        {"name": "where_do_you_currently_live", "values": ["Gurgaon"]},
        {"name": "which_flat/apartment_size_do_you_need", "values": ["3_bhk"]},
    ]}

    spine, _ = build_meta([normalise_pushed(meta_leads.flatten(lead))])
    assert len(spine) == 1
    row = spine[0]

    # the shared identity: the same buyer from the sheet collides with this on purpose
    assert row["origin_key"] == "meta:9999799588"
    assert row["name"] == "Rahul Sharma"
    assert row["email"] == "rahul@example.com"
    # city is the DEMAND side; where they live now is a different column
    assert row["city"] == "Noida"
    assert row["current_location"] == "Gurgaon"
    # Meta's export type-tag is shed, not stored verbatim
    assert row["zip_code"] == "201305"
    # the verbatim payload survives for anything nobody mapped
    assert row["raw"]["your_budget_range"] == "up_to_₹75_lacs"


def test_a_lead_with_no_phone_is_skipped_not_failed():
    """Phone is the identity. A half-filled form row is normal, not an error."""
    lead = {"field_data": [{"name": "full_name", "values": ["No Phone"]}]}
    spine, _ = build_meta([normalise_pushed(meta_leads.flatten(lead))])
    assert spine == []


def test_the_fetch_asks_for_every_attribution_field():
    """The funnel is campaign -> ad set -> ad -> lead; a dropped field breaks it."""
    for field in ("field_data", "campaign_id", "campaign_name", "adset_id", "ad_id",
                  "ad_name", "form_id", "created_time"):
        assert field in meta_leads.LEAD_FIELDS


def test_the_webhook_payload_is_stored_as_sent():
    """raw_webhook is the only record of what Meta actually delivered."""
    payload = {"entry": [{"changes": [{"field": "leadgen", "value": {"leadgen_id": "L1"}}]}]}
    assert json.loads(json.dumps(payload)) == payload
    assert "raw_webhook" in str(meta_leads.UPSERT_EVENT)


# ---- the list endpoint's SQL ---------------------------------------------------


def test_the_log_joins_its_lead_on_origin_key_not_leadgen_id():
    """`leads.meta_lead_id` only ever holds the FIRST delivery's id (STAMP_LEAD is
    guarded on IS NULL), so joining the log on it would render every repeat submission
    from the same buyer as an orphan with no lead."""
    from app.routers.meta import LIST_EVENTS

    sql = str(LIST_EVENTS)
    assert "l.origin_key = e.origin_key" in sql
    assert "l.meta_lead_id = e.meta_lead_id" not in sql


def test_the_log_reads_newest_first():
    from app.routers.meta import LIST_EVENTS

    assert "ORDER BY e.received_at DESC" in str(LIST_EVENTS)


def test_every_delivery_records_which_lead_it_landed_on():
    """Without this the join above has nothing to join on."""
    assert "origin_key = :origin_key" in str(meta_leads.MARK_EVENT)
