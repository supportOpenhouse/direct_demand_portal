"""Audit logging — decides what's worth recording, who the actor is, a human label
for each action, and the insert/query against audit_logs. Inserts are fire-and-forget
(never block or break a request); a Neon outage just drops the log line."""
import logging
import re

import jwt
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..db import neon_engine
from ..models import AuditLog

log = logging.getLogger("audit")

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_OH_UID_RE = re.compile(r"^OH[A-Za-z]*\d+$")


def _mask_seg(seg: str) -> str:
    return "{id}" if (_UUID_RE.match(seg) or seg.isdigit() or _OH_UID_RE.match(seg)) else seg


def mask_path(path: str) -> str:
    """'/v1/leads/<uuid>/confirm' -> '/v1/leads/{id}/confirm' (for grouping/labels)."""
    return "/".join(_mask_seg(s) for s in path.split("/"))


# human labels for the routes worth naming; anything else falls back to "METHOD route"
_LABELS = {
    ("POST", "/v1/auth/google"): "Signed in",
    ("POST", "/v1/leads/{id}/confirm"): "Qualified a lead",
    ("POST", "/v1/leads/{id}/reject"): "Rejected a lead",
    ("POST", "/v1/leads/{id}/assign"): "Assigned a lead",
    ("POST", "/v1/leads/bulk-assign"): "Bulk-assigned leads",
    ("PATCH", "/v1/leads/{id}/source-data"): "Edited lead data",
    ("POST", "/v1/leads/{id}/notes"): "Added a note",
    ("POST", "/v1/leads/{id}/visits"): "Saved a visit plan",
    ("POST", "/v1/visits/book"): "Booked visits on the app",
    ("POST", "/v1/supply/{id}/priority"): "Marked supply priority",
    ("POST", "/v1/users"): "Added a user",
    ("PATCH", "/v1/users/{id}"): "Updated a user",
    ("DELETE", "/v1/users/{id}"): "Removed a user",
    ("POST", "/v1/inventory/sync"): "Triggered inventory sync",
    ("GET", "/v1/leads/{id}"): "Viewed a lead",
}


def label_for(method: str, route: str) -> str:
    return _LABELS.get((method, route)) or f"{method} {route}"


def category_for(method: str, route: str) -> str:
    if route == "/v1/auth/google":
        return "auth"
    return "read" if method == "GET" else "write"


def should_log(method: str, path: str) -> bool:
    """Log every write + login, plus lead-detail views. Skip health checks, the logs
    page itself, OPTIONS preflight, and high-frequency list/poll GET refetches."""
    if method == "OPTIONS":
        return False
    # /v1/gupshup: an inbound-webhook POST per WhatsApp message would flood audit_logs
    if path.startswith(("/v1/health", "/v1/logs", "/v1/gupshup")):
        return False
    if method == "GET":  # only the meaningful detail view, not list refetches
        return path.startswith("/v1/leads/") and path.count("/") == 3
    return True


def actor_from_request(request) -> dict | None:
    """Best-effort actor from the bearer JWT (or the synthetic admin when auth is off)."""
    settings = get_settings()
    if not settings.auth_enabled:
        return {"email": "open@local", "name": "Open Access", "role": "admin"}
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        payload = jwt.decode(auth.split(" ", 1)[1].strip(), settings.JWT_SECRET, algorithms=["HS256"])
        return {"email": payload.get("email"), "name": payload.get("name"), "role": payload.get("role")}
    except jwt.PyJWTError:
        return None


async def record(*, actor, method, path, status, duration_ms, ip, request_id) -> None:
    engine = neon_engine()
    if engine is None:
        return
    route = mask_path(path)
    actor = actor or {}
    try:
        async with engine.begin() as conn:
            await conn.execute(pg_insert(AuditLog).values(
                actor_email=actor.get("email"), actor_name=actor.get("name"), actor_role=actor.get("role"),
                action=label_for(method, route), category=category_for(method, route),
                method=method, path=path, route=route,
                status_code=status, duration_ms=duration_ms, ip=ip, request_id=request_id,
            ))
    except Exception:  # noqa: BLE001 — audit must never break the request
        log.warning("audit insert failed", exc_info=True)


async def query_logs(*, actor=None, category=None, method=None, q=None, status=None,
                     date_from=None, date_to=None, limit=50, offset=0) -> dict:
    engine = neon_engine()
    if engine is None:
        return {"items": [], "total": 0}
    where, params = [], {}
    if actor:
        where.append("actor_email = :actor"); params["actor"] = actor
    if category:
        where.append("category = :cat"); params["cat"] = category
    if method:
        where.append("method = :method"); params["method"] = method.upper()
    if status:
        where.append("status_code = :status"); params["status"] = status
    if q:
        where.append("(action ILIKE :q OR path ILIKE :q OR actor_email ILIKE :q OR actor_name ILIKE :q)")
        params["q"] = f"%{q}%"
    if date_from:
        where.append("created_at >= :df"); params["df"] = date_from
    if date_to:
        where.append("created_at <= :dt"); params["dt"] = date_to
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    async with engine.connect() as conn:
        total = (await conn.execute(text(f"SELECT count(*) FROM audit_logs{clause}"), params)).scalar()
        rows = (await conn.execute(text(
            "SELECT id, created_at, actor_email, actor_name, actor_role, action, category, "
            f"method, path, status_code, duration_ms, ip FROM audit_logs{clause} "
            "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
            {**params, "limit": limit, "offset": offset})).mappings().all()
    items = [{
        "id": str(r["id"]),
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "actor_email": r["actor_email"], "actor_name": r["actor_name"], "actor_role": r["actor_role"],
        "action": r["action"], "category": r["category"], "method": r["method"], "path": r["path"],
        "status_code": r["status_code"], "duration_ms": r["duration_ms"], "ip": r["ip"],
    } for r in rows]
    return {"items": items, "total": total}


async def list_actors() -> list[str]:
    engine = neon_engine()
    if engine is None:
        return []
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT DISTINCT actor_email FROM audit_logs WHERE actor_email IS NOT NULL ORDER BY 1"))).all()
    return [r[0] for r in rows]
