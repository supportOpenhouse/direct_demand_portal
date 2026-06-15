"""User management — admin-only. Add/edit/disable the people allowed to log in,
and map each to their leads via the sheet's 'Assigned to' name."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..core.auth import assignment_aliases, require_admin
from ..db import neon_engine
from ..models import User

router = APIRouter(tags=["users"], dependencies=[Depends(require_admin)])

ROLES = {"admin", "cm", "rm"}


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
            "SELECT id, email, name, picture, role, assignment_name, active, last_login_at, created_at "
            "FROM users ORDER BY created_at"
        ))
        users = [dict(m) for m in res.mappings()]
        counts = await _lead_counts(conn)
    return {"items": [
        {
            "id": str(u["id"]), "email": u["email"], "name": u["name"], "picture": u["picture"],
            "role": u["role"], "maps_to": _first_name(u["name"]),  # the name we match in the sheet
            "active": u["active"],
            "last_login_at": u["last_login_at"].isoformat() if u["last_login_at"] else None,
            "matched_leads": _matched(u, counts),
        }
        for u in users
    ]}


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    role: str = "rm"


@router.post("/users")
async def create_user(payload: UserCreate):
    if payload.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(ROLES)}")
    engine = neon_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="database not configured")
    async with engine.begin() as conn:
        stmt = pg_insert(User).values(
            email=str(payload.email).lower(), name=payload.name.strip(), role=payload.role, active=True,
        ).on_conflict_do_nothing(index_elements=[User.email]).returning(User.id)
        row = (await conn.execute(stmt)).first()
        if row is None:
            raise HTTPException(status_code=409, detail="a user with that email already exists")
    return {"id": str(row[0]), "status": "ok"}


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None


@router.patch("/users/{user_id}")
async def update_user(user_id: UUID, payload: UserUpdate):
    if payload.role is not None and payload.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(ROLES)}")
    sets, params = [], {"id": user_id}
    for field in ("name", "role", "active"):
        val = getattr(payload, field)
        if val is not None:
            sets.append(f"{field} = :{field}")
            params[field] = val
    if not sets:
        return {"status": "noop"}
    engine = neon_engine()
    async with engine.begin() as conn:
        res = await conn.execute(text(f"UPDATE users SET {', '.join(sets)} WHERE id = :id"), params)
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="user not found")
    return {"status": "ok"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: UUID):
    engine = neon_engine()
    async with engine.begin() as conn:
        res = await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="user not found")
    return {"status": "ok"}
