"""DESTRUCTIVE: wipe demo/transactional data for a production go-live.

Deletes ALL leads (and their source/confirmed data, activity, reminders, visits,
recordings), all inventory/supply units, Gold Mine buckets, interests and society
insights. KEEPS: users, teams, societies, localities, settings, API keys.

    uv run python -m app.purge_demo --yes
    uv run python -m app.purge_demo --yes --remove-demo-users

--remove-demo-users also deletes the seeded fake logins (admin@/cm@/rm1..3@openhouse.in).
support@openhouse.in is always kept. Refuses to run without --yes.
"""

import argparse
import asyncio

from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.models import (
    Bucket,
    BucketMember,
    Interest,
    Inventory,
    Lead,
    LeadActivity,
    LeadConfirmedData,
    LeadPreferredLocality,
    LeadShortlistSociety,
    LeadSourceData,
    Recording,
    Reminder,
    SocietyInsight,
    SupplyUnit,
    User,
    Visit,
    VisitStop,
)

DEMO_USERS = (
    "admin@openhouse.in",
    "cm@openhouse.in",
    "rm1@openhouse.in",
    "rm2@openhouse.in",
    "rm3@openhouse.in",
)

# FK-safe deletion order (children before parents, no reliance on DB cascades).
PURGE_ORDER = (
    BucketMember,
    Bucket,
    Interest,
    Recording,
    VisitStop,
    Visit,
    Reminder,
    LeadActivity,
    LeadShortlistSociety,
    LeadPreferredLocality,
    LeadConfirmedData,
    LeadSourceData,
    Lead,
    Inventory,
    SupplyUnit,
    SocietyInsight,
)


async def purge(remove_demo_users: bool) -> None:
    async with SessionLocal() as session:
        for model in PURGE_ORDER:
            count = (await session.execute(select(func.count()).select_from(model))).scalar_one()
            await session.execute(delete(model))
            print(f"deleted {count:>4}  {model.__tablename__}")
        if remove_demo_users:
            res = await session.execute(
                delete(User).where(func.lower(User.email).in_(DEMO_USERS))
            )
            print(f"deleted {res.rowcount:>4}  demo users ({', '.join(DEMO_USERS)})")
        await session.commit()
    print("\nDone. Kept: users/teams (minus demo users if requested), societies, "
          "localities, settings, api keys.")


def main() -> None:
    p = argparse.ArgumentParser(prog="app.purge_demo", description=__doc__)
    p.add_argument("--yes", action="store_true", help="confirm the irreversible wipe")
    p.add_argument("--remove-demo-users", action="store_true",
                   help="also delete the seeded demo logins (never support@openhouse.in)")
    a = p.parse_args()
    if not a.yes:
        p.error("this irreversibly deletes data — re-run with --yes to confirm")
    asyncio.run(purge(a.remove_demo_users))


if __name__ == "__main__":
    main()
