"""Parsing Huvo's call-update payload.

Their contract (Huvo CRM Call Update Webhook) delivers one JSON envelope per
completed call: {status, call_details, analytics_data}. Everything here is pure —
given a payload, produce the row we'd store — so the shape can be tested without a
database or a webhook.

Three things the contract does NOT give us, which is most of why this module exists:
  * no lead id — `from_number` is the only link back to us, and it isn't unique;
  * no delivery id and no retry policy — so idempotency has to be synthesised;
  * "required" means the key is present, not that it has a value. 13 of the 19
    analytics fields are nullable, so a null must read as "the caller didn't say".
"""
import hashlib
import json
import re
from datetime import datetime

# 1 crore = 100 lacs. budget_crores is a STRING in their schema and this app stores
# lacs, so the factor is the whole point — copying the number across understates a
# budget a hundredfold.
LACS_PER_CRORE = 100


def digits10(phone: str | None) -> str:
    """Last 10 digits, or "" when there aren't 10.

    Matches _digits() in routers/bonvoice.py deliberately: from_number arrives however
    the caller's carrier formatted it, and if this disagreed with the rest of the app
    nothing would ever join. Short input yields "" rather than a truncation that could
    match the wrong lead.
    """
    d = re.sub(r"\D", "", phone or "")
    return d[-10:] if len(d) >= 10 else ""


def parse_dt(raw: str | None) -> datetime | None:
    """ISO 8601 -> aware datetime, else None.

    Only the *_dt fields are machine-readable; their siblings carry prose like
    "tomorrow evening". The docs promise ISO only "when a date and time are
    available", so failing to parse is normal — and inventing a time from prose would
    put a real callback in an RM's queue at the wrong hour.
    """
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return parsed if parsed.tzinfo else None


def _budget_lacs(raw: str | None) -> float | None:
    """"1.2" (crores) -> 120.0 (lacs). Anything not a plain number -> None.

    The field is free text, so "1-1.5" and "around 2 cr" are both legal. None is the
    honest answer for those; 0 would read as a real budget of nothing.
    """
    if raw is None:
        return None
    try:
        return float(str(raw).strip()) * LACS_PER_CRORE
    except (ValueError, TypeError):
        return None


def campaign_of(envelope: dict) -> str | None:
    """Which campaign placed this call.

    Huvo now sends `campaign_name` inside call_details, and that is authoritative —
    it's what their own system recorded for the call.

    The fallback is the CSV import's `Campaign` column, kept under payload._import.
    717 backfilled rows predate the live field and carry the campaign only there;
    without the fallback every one of them would read as having no campaign.

    A blank live value falls through rather than winning: an empty string is not an
    answer, and letting it shadow a known campaign would lose information.
    """
    live = ((envelope.get("call_details") or {}).get("campaign_name") or "").strip()
    if live:
        return live
    imported = (((envelope.get("_import") or {}).get("extra") or {})
                .get("Campaign") or "").strip()
    return imported or None


def dedupe_key(envelope: dict) -> str:
    """A stable id for one call.

    from_number + start_time is the natural key — one update per call — but
    start_time is nullable, so when it's missing we fall back to a digest of the whole
    envelope. That still collapses a byte-identical retry, which is the actual failure
    mode given the contract defines no delivery id and no retry policy.
    """
    analytics = envelope.get("analytics_data") or {}
    details = envelope.get("call_details") or {}
    number, start = digits10(analytics.get("from_number")), details.get("start_time")
    if number and start:
        return f"{number}|{start}"
    blob = json.dumps(envelope, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


def extract(envelope: dict) -> dict:
    """The row we store: a focused projection plus the envelope verbatim.

    The projection is only the fields a list or a report would filter and sort on.
    Everything else — lead_score's siblings, rsvp_status, interest_reason, purpose —
    has no column in this app, so `payload` keeps the original: if the outcome mapping
    turns out wrong later, it can be re-derived instead of having been thrown away.
    """
    analytics = envelope.get("analytics_data") or {}
    details = envelope.get("call_details") or {}

    score = analytics.get("lead_score")
    try:
        score = float(score) if score is not None else None
    except (ValueError, TypeError):
        score = None

    return {
        "dedupe_key": dedupe_key(envelope),
        "campaign_name": campaign_of(envelope),
        "from_number": digits10(analytics.get("from_number")),
        "caller_name": analytics.get("name"),
        "call_outcome": analytics.get("call_outcome"),
        "is_interested": analytics.get("is_interested"),
        "rsvp_status": analytics.get("rsvp_status"),
        "lead_score": score,
        "budget_lacs": _budget_lacs(analytics.get("budget_crores")),
        # their docs: where a field appears in both objects the analytics value is
        # kept and the call_details duplicate is omitted — so read analytics first
        "summary": analytics.get("summary_of_call") or details.get("summary"),
        "recording_url": details.get("recording_url"),
        "duration_sec": details.get("duration_sec"),
        "started_at": parse_dt(details.get("start_time")),
        "ended_at": parse_dt(details.get("end_time")),
        "follow_up_at": parse_dt(analytics.get("follow_up_time_dt")),
        "payload": envelope,
    }
