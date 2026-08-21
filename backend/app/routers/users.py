"""User management — admin-only. Add/edit/disable the people allowed to log in,
and map each to their leads via the sheet's 'Assigned to' name."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..core.auth import assignment_aliases, force_logout_all, forget_user, require_admin
from ..db import neon_engine
from ..services import activity
from ..models import User

router = APIRouter(tags=["users"], dependencies=[Depends(require_admin)])

# test_rm is an RM in every respect except that WhatsApp never assigns it a
# conversation (services/wa_assign.py) and the dialer picker tags it TEST. Row scoping,
# Live Calls and the worklists all treat it as `rm` via core.auth.is_calling_rm.
ROLES = {"admin", "rm", "test_rm"}


def _first_name(name: str | None) -> str | None:
    return name.strip().split()[0] if name and name.strip() else None


async def _lead_counts(conn) -> list[dict]:
    res = await conn.execute(text(
        "SELECT lower(assigned_to) AS a, count(*) c FROM leads WHERE assigned_to IS NOT NULL GROUP BY lower(assigned_to)"
    ))
    return [{"a": r[0], "c": r[1]} for r in res]


def _matched(user_row: dict, counts: list[dict]) -> int:
    aliases = set(assignment_aliases({"name": user_row["name"]}))
    return sum(c["c"] for c in counts if c["a"] in aliases)


@router.get("/users")
async def list_users():
    engine = neon_engine()
    if engine is None:
        return {"items": []}
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT id, email, name, picture, role, assignment_name, phone, smid, active, last_login_at, created_at "
            "FROM users ORDER BY created_at"
        ))
        users = [dict(m) for m in res.mappings()]
        counts = await _lead_counts(conn)
    return {"items": [
        {
            "id": str(u["id"]), "email": u["email"], "name": u["name"], "picture": u["picture"],
            "role": u["role"], "maps_to": _first_name(u["name"]),  # the name we match in the sheet
            "smid": u["smid"], "phone": u["phone"], "active": u["active"],
            "last_login_at": u["last_login_at"].isoformat() if u["last_login_at"] else None,
            "matched_leads": _matched(u, counts),
        }
        for u in users
    ]}


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    role: str = "rm"
    smid: int | None = None
    phone: str | None = None  # mobile that click-to-call rings first


@router.post("/users")
async def create_user(payload: UserCreate, actor: dict = Depends(require_admin)):
    if payload.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(ROLES)}")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    async with engine.begin() as conn:
        stmt = pg_insert(User).values(
            email=str(payload.email).lower(), name=payload.name.strip(), role=payload.role,
            smid=payload.smid, phone=payload.phone, active=True,
        ).on_conflict_do_nothing(index_elements=[User.email]).returning(User.id)
        row = (await conn.execute(stmt)).first()
        if row is None:
            raise HTTPException(status_code=409, detail="a user with that email already exists")
        await activity.record(conn, activity.row_for(
            activity.Actor.of(actor), entity_type="user",
            entity_id=str(payload.email).lower(), action="user_created",
            metadata={"role": payload.role, "name": payload.name.strip()}))
    return {"id": str(row[0]), "status": "ok"}


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    smid: int | None = None
    phone: str | None = None


@router.patch("/users/{user_id}")
async def update_user(user_id: UUID, payload: UserUpdate,
                      actor: dict = Depends(require_admin)):
    if payload.role is not None and payload.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(ROLES)}")
    sets, params = [], {"id": user_id}
    for field in ("name", "role", "active", "smid", "phone"):
        val = getattr(payload, field)
        if val is not None:
            sets.append(f"{field} = :{field}")
            params[field] = val
    if not sets:
        return {"status": "noop"}
    engine = neon_engine()
    async with engine.begin() as conn:
        # Read first: "who made whom an admin" is the question an audit trail exists to
        # answer, and it needs the prior role, not just the new one.
        before = (await conn.execute(text(
            "SELECT email, name, role, active FROM users WHERE id = :id"),
            {"id": user_id})).mappings().first()
        res = await conn.execute(text(f"UPDATE users SET {', '.join(sets)} WHERE id = :id"), params)
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="user not found")

        me = activity.Actor.of(actor)
        events = activity.changes_between(
            me, "user", before["email"], dict(before),
            {k: v for k, v in params.items() if k != "id"})
        # Role and active get their own verbs — they're the two that change what a
        # person can DO, and burying them in a generic "update" makes them unfilterable.
        for e in events:
            if e["field"] == "role":
                e["action"] = "role_changed"
            elif e["field"] == "active":
                e["action"] = "user_activated" if e["after_value"] == "true" else "user_deactivated"
        await activity.record(conn, events)
    forget_user(user_id)  # a role/active edit must bite now, not when their token lapses
    return {"status": "ok"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: UUID):
    engine = neon_engine()
    async with engine.begin() as conn:
        res = await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="user not found")
    forget_user(user_id)
    return {"status": "ok"}


@router.post("/sessions/logout-all")
async def logout_all_sessions(user: dict = Depends(require_admin)):
    """Force every user (including the caller) to sign in again."""
    await force_logout_all(user.get("email") or "admin")
    # One click invalidates every session in the company. If anything belongs in an
    # audit trail, it's this.
    engine = neon_engine()
    if engine is not None:
        async with engine.begin() as conn:
            await activity.record(conn, activity.row_for(
                activity.Actor.of(user), entity_type="auth", entity_id=None,
                action="force_logout_all"))
    return {"status": "ok"}


class ReassignPayload(BaseModel):
    to_user_id: UUID


@router.post("/users/{user_id}/reassign")
async def reassign_leads(user_id: UUID, payload: ReassignPayload):
    """Move every lead owned by `user_id` to `to_user_id`. Called when an admin
    disables/removes a user so their leads don't end up orphaned. Matches by the
    sheet's 'Assigned to' name (first or full) and rewrites it to the target's full
    name, keeping the app's name-based assignment consistent."""
    if user_id == payload.to_user_id:
        raise HTTPException(status_code=422, detail="pick a different user to reassign to")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    async with engine.begin() as conn:
        rows = {str(r["id"]): r["name"] for r in (await conn.execute(
            text("SELECT id, name FROM users WHERE id = ANY(:ids)"),
            {"ids": [user_id, payload.to_user_id]},
        )).mappings()}
        from_name = rows.get(str(user_id))
        to_name = rows.get(str(payload.to_user_id))
        if from_name is None or to_name is None:
            raise HTTPException(status_code=404, detail="user not found")
        aliases = assignment_aliases({"name": from_name})
        if not aliases:
            return {"status": "ok", "moved": 0}
        res = await conn.execute(
            text("UPDATE leads SET assigned_to = :to WHERE lower(assigned_to) = ANY(:aliases)"),
            {"to": to_name, "aliases": aliases},
        )
    return {"status": "ok", "moved": res.rowcount}
