"""Manage the login allowlist (the users table) without SQL.

Only emails present (and active) in the users table can sign in with Google;
their role comes from the row. Run from backend/ with DATABASE_URL set (.env works):

    uv run python -m app.add_user list
    uv run python -m app.add_user add rahul@openhouse.in "Rahul Verma" rm --team "Team Gurgaon"
    uv run python -m app.add_user add priya@openhouse.in "Priya Nair" cm --team "Team Noida"
    uv run python -m app.add_user add ops@openhouse.in "Ops Admin" admin
    uv run python -m app.add_user deactivate rm3@openhouse.in

`add` is an upsert: an existing email gets its name/role/team/active updated.
A `--team` that doesn't exist yet is created; adding a cm to a team makes them its
closing manager.
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Team, User

ROLES = ("admin", "cm", "rm")


async def _get_user(session, email: str) -> User | None:
    return (
        await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()


async def cmd_list() -> None:
    async with SessionLocal() as session:
        users = (await session.execute(select(User).order_by(User.role, User.email))).scalars().all()
        teams = {t.id: t.name for t in (await session.execute(select(Team))).scalars().all()}
        if not users:
            print("users table is empty")
            return
        w = max(len(u.email) for u in users) + 2
        for u in users:
            team = teams.get(u.team_id, "-") if u.team_id else "-"
            flag = "" if u.active else "  [INACTIVE]"
            print(f"{u.email:<{w}} {u.role:<6} {u.name:<24} team={team}{flag}")


async def cmd_add(email: str, name: str, role: str, team_name: str | None, phone: str | None) -> None:
    async with SessionLocal() as session:
        team = None
        if team_name:
            team = (
                await session.execute(select(Team).where(Team.name == team_name))
            ).scalar_one_or_none()
            if team is None:
                team = Team(name=team_name)
                session.add(team)
                await session.flush()
                print(f"created team '{team_name}'")

        user = await _get_user(session, email)
        if user is None:
            user = User(email=email.strip().lower(), name=name, role=role, active=True)
            session.add(user)
            action = "added"
        else:
            user.name, user.role, user.active = name, role, True
            action = "updated"
        if phone:
            user.phone = phone
        if team:
            user.team_id = team.id
            if role == "cm":
                team.cm_user_id = user.id

        await session.flush()
        if team and role == "cm":
            team.cm_user_id = user.id
        await session.commit()
        print(f"{action}: {user.email} role={role}" + (f" team={team_name}" if team_name else ""))


async def cmd_deactivate(email: str) -> None:
    async with SessionLocal() as session:
        user = await _get_user(session, email)
        if user is None:
            print(f"no such user: {email}")
            sys.exit(1)
        user.active = False
        await session.commit()
        print(f"deactivated: {user.email} (can no longer log in)")


def main() -> None:
    p = argparse.ArgumentParser(prog="app.add_user", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list all users")

    pa = sub.add_parser("add", help="add or update a user (upsert by email)")
    pa.add_argument("email")
    pa.add_argument("name")
    pa.add_argument("role", choices=ROLES)
    pa.add_argument("--team", help="team name (created if missing; cm becomes its manager)")
    pa.add_argument("--phone")

    pd = sub.add_parser("deactivate", help="block a user from logging in")
    pd.add_argument("email")

    a = p.parse_args()
    if a.cmd == "list":
        asyncio.run(cmd_list())
    elif a.cmd == "add":
        asyncio.run(cmd_add(a.email, a.name, a.role, a.team, a.phone))
    elif a.cmd == "deactivate":
        asyncio.run(cmd_deactivate(a.email))


if __name__ == "__main__":
    main()
