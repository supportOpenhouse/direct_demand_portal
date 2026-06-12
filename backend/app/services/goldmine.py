"""Gold Mine bucketing (HANDOVER §6.5): rebuild buckets/members against ALL leads —
including dormant/terminal stages, since the Gold Mine exists to reactivate them."""
import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bucket, BucketMember, Inventory, Lead, SupplyUnit
from app.services.matching import build_lead_profile, score_unit

log = logging.getLogger("app.goldmine")


async def rematch(session: AsyncSession, unit: Inventory | SupplyUnit | None = None) -> int:
    """Upsert one bucket per unit (or just `unit`) and rebuild its members from
    every lead via the matching engine. Returns the number of buckets processed."""
    leads = (await session.execute(select(Lead))).scalars().all()
    profiles = [(lead, build_lead_profile(lead)) for lead in leads]

    if unit is not None:
        units: list[Inventory | SupplyUnit] = [unit]
    else:
        units = list((await session.execute(select(Inventory))).scalars().all())
        units += list((await session.execute(select(SupplyUnit))).scalars().all())

    processed = 0
    for u in units:
        is_inventory = isinstance(u, Inventory)
        col = Bucket.inventory_id if is_inventory else Bucket.supply_unit_id
        bucket = (await session.execute(select(Bucket).where(col == u.id))).scalar_one_or_none()
        if bucket is None:
            bucket = Bucket(
                id=uuid.uuid4(),
                inventory_id=u.id if is_inventory else None,
                supply_unit_id=None if is_inventory else u.id,
            )
            session.add(bucket)
            await session.flush()
        else:
            await session.execute(delete(BucketMember).where(BucketMember.bucket_id == bucket.id))

        for lead, profile in profiles:
            is_match, score, matched_on = score_unit(profile, u)
            if is_match:
                session.add(
                    BucketMember(
                        bucket_id=bucket.id, lead_id=lead.id, score=score, matched_on=matched_on
                    )
                )
        processed += 1

    await session.commit()
    log.info("goldmine rematch: %d bucket(s) rebuilt over %d lead(s)", processed, len(leads))
    return processed
