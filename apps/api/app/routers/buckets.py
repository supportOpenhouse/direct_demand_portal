"""Gold Mine — admin + cm only (RM gets 403; nav hidden client-side)."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import lead_scope_filter, require_roles
from app.core.errors import ApiError
from app.core.utils import utcnow
from app.db import get_session
from app.models import Bucket, Interest, Lead, LeadActivity, User
from app.schemas.requests import BroadcastRequest
from app.services import goldmine, whatsapp
from app.services.matching import match_pct
from app.services.serializers import lead_row, unit_payload

router = APIRouter(tags=["goldmine"], dependencies=[Depends(require_roles("admin", "cm"))])


async def _visible_lead_ids(session: AsyncSession, user: User) -> set | None:
    crit = lead_scope_filter(user)
    if crit is None:
        return None
    return set((await session.execute(select(Lead.id).where(crit))).scalars())


def _bucket_unit(bucket: Bucket):
    if bucket.inventory_id is not None:
        return bucket.inventory, "inventory"
    return bucket.supply_unit, "supply"


@router.get("/buckets")
async def list_buckets(
    user: User = Depends(require_roles("admin", "cm")),
    session: AsyncSession = Depends(get_session),
):
    visible = await _visible_lead_ids(session, user)
    interest_counts = dict(
        (
            await session.execute(
                select(Interest.supply_unit_id, func.count()).group_by(Interest.supply_unit_id)
            )
        ).all()
    )
    buckets = (await session.execute(select(Bucket))).scalars().all()
    now = utcnow()
    out = []
    for bucket in buckets:
        unit, kind = _bucket_unit(bucket)
        if unit is None:
            continue
        members = [
            m for m in bucket.members if visible is None or m.lead_id in visible
        ]
        out.append(
            {
                "id": str(bucket.id),
                "unit": unit_payload(
                    unit, kind, interest_counts.get(bucket.supply_unit_id, 0) if kind == "supply" else 0
                ),
                "unit_kind": kind,
                "member_count": len(members),
                "members": [
                    {
                        "lead": lead_row(m.lead, now),
                        "score": m.score,
                        "match_pct": match_pct(m.score),
                        "matched_on": m.matched_on or [],
                    }
                    for m in members
                ],
            }
        )
    out.sort(key=lambda b: b["member_count"], reverse=True)
    return out


@router.post("/buckets/rematch")
async def rematch_buckets(
    user: User = Depends(require_roles("admin", "cm")),
    session: AsyncSession = Depends(get_session),
):
    n = await goldmine.rematch(session)
    return {"buckets": n}


@router.post("/buckets/{bucket_id}/broadcast")
async def broadcast_bucket(
    bucket_id: uuid.UUID,
    payload: BroadcastRequest,
    user: User = Depends(require_roles("admin", "cm")),
    session: AsyncSession = Depends(get_session),
):
    bucket = await session.get(Bucket, bucket_id)
    if bucket is None:
        raise ApiError(404, "Bucket not found")
    unit, kind = _bucket_unit(bucket)
    if unit is None:
        raise ApiError(404, "Bucket unit not found")

    visible = await _visible_lead_ids(session, user)
    members = [m for m in bucket.members if visible is None or m.lead_id in visible]

    sent = 0
    for member in members:
        lead = member.lead
        if lead is None:
            continue
        if payload.mode == "whatsapp":
            whatsapp.stub_send(
                session,
                lead,
                f"🏠 {unit.name} — {unit.society}, {unit.city}. This unit matches your requirement; "
                "reply YES to book a visit.",
                actor_id=user.id,
                event="whatsapp_sent",
            )
        else:  # call_list
            session.add(
                LeadActivity(
                    lead_id=lead.id,
                    event="added to call list",
                    remark=f"Call about {unit.name} ({unit.society})",
                    actor_id=user.id,
                )
            )
        sent += 1
    await session.commit()
    return {"sent": sent}
