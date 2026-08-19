"""Activity log — an append-only record of WHAT CHANGED, written in the same
transaction as the change.

Replaces audit_logs, which logged HTTP requests: method, path, status. That answered
"a POST to /v1/leads/{id}/confirm returned 200" and nothing a person actually wants —
not which lead, not which field, not from what to what. It was also written from
middleware after the response had gone out, so a rolled-back transaction still logged
a success.

The shape here follows the pattern already proven on the other dashboard
(docs/activity_logs/activity_log.md): entity_type · entity_id · action · field ·
before_value · after_value · metadata. Two consequences worth stating:

  * The caller passes its own connection, so the log row commits with the change or
    dies with it. The log cannot drift from the data.
  * Values are TEXT. A stage is a string, miss_count an int, is_hot a bool,
    follow_up_at a datetime — one column per type would be absurd, and the log is read
    by people, not joined on.
"""
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text

log = logging.getLogger("activity")

# Fields whose change is interesting enough to be its own action rather than a generic
# "update". Stage is the spine of this app — every lead page is an equality on it — so
# folding it into `update` would make the single most-filtered event unfilterable.
_ACTION_FOR_FIELD = {
    "stage": "stage_change",
    "assigned_to": "assigned",
}

# Fields holding an id/email that reads as noise. The display name is shown and the raw
# value is kept in metadata, so entries stay traceable — the doc's rule.
_HUMANISED_FIELDS = {"assigned_to", "assigned_rm", "actor", "owner"}

_INSERT = text("""
    INSERT INTO activity_log
           (id, actor_email, actor_name, actor_role, entity_type, entity_id,
            action, field, before_value, after_value, metadata, created_at)
    VALUES (gen_random_uuid(), :actor_email, :actor_name, :actor_role, :entity_type,
            :entity_id, :action, :field, :before_value, :after_value,
            CAST(:metadata AS jsonb), now())
""")


@dataclass(frozen=True)
class Actor:
    """Who did it. None where a background job did — syncs and the dialer act with
    nobody signed in, and those events still have to be loggable."""

    email: str | None = None
    name: str | None = None
    role: str | None = None

    @classmethod
    def of(cls, user: dict | None) -> "Actor | None":
        if not user:
            return None
        return cls(email=user.get("email"), name=user.get("name"), role=user.get("role"))


def _str(value: Any) -> str | None:
    """Stringify for storage. None stays None — "None" would read in the UI as a real
    prior value rather than as "there wasn't one"."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def row_for(actor: Actor | None, *, entity_type: str, entity_id: str | None,
            action: str, field: str | None = None,
            before: Any = None, after: Any = None,
            metadata: dict | None = None) -> dict:
    """One log row, ready to insert. Pure — so the shape is testable without a DB."""
    return {
        "actor_email": actor.email if actor else None,
        "actor_name": actor.name if actor else None,
        "actor_role": actor.role if actor else None,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "action": action,
        "field": field,
        "before_value": _str(before),
        "after_value": _str(after),
        "metadata": dict(metadata or {}),
    }


def changes_between(actor: Actor | None, entity_type: str, entity_id: str | None,
                    before: dict, after: dict,
                    metadata: dict | None = None) -> list[dict]:
    """One row per field that actually changed.

    Only keys PRESENT in `after` are considered: a PATCH sends just what it touches,
    and treating a missing key as null would log every untouched column as wiped.
    Unchanged fields are skipped — an edit form posts everything, and logging all of it
    would bury the one field that moved.
    """
    rows = []
    for key, new in after.items():
        old = before.get(key)
        if old == new:
            continue
        rows.append(row_for(actor, entity_type=entity_type, entity_id=entity_id,
                            action=_ACTION_FOR_FIELD.get(key, "update"),
                            field=key, before=old, after=new, metadata=metadata))
    return rows


def humanize(row: dict, names: dict[str, str]) -> dict:
    """Swap an id for its display name, keeping the id in metadata.

    "assigned_to: 3f2a… → 9c81…" is unreadable; "Asha → Vikram" is the event. The raw
    values stay under metadata so an entry can still be traced back. An id with no
    known name is left as-is rather than blanked — a missing name shouldn't erase the
    only evidence of what happened.
    """
    if row.get("field") not in _HUMANISED_FIELDS:
        return row
    meta = dict(row.get("metadata") or {})
    for side in ("before", "after"):
        raw = row.get(f"{side}_value")
        if raw is None:
            continue
        meta[f"{side}_id"] = raw
        row[f"{side}_value"] = names.get(raw, raw)
    row["metadata"] = meta
    return row


async def record(conn, rows: list[dict] | dict) -> int:
    """Write on the CALLER'S connection, so these commit with the change they describe.

    Never raises: a failed log line must not roll back real work. That is the one place
    this differs from the data it records — losing an audit row is bad, losing the
    lead update it describes is worse.
    """
    batch = [rows] if isinstance(rows, dict) else list(rows)
    if not batch:
        return 0
    try:
        await conn.execute(_INSERT, [
            {**r, "metadata": json.dumps(r.get("metadata") or {}, default=str)}
            for r in batch
        ])
        return len(batch)
    except Exception:  # noqa: BLE001
        log.exception("activity: failed to record %d row(s)", len(batch))
        return 0
