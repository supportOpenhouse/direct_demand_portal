import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import apply_lead_scope, get_current_user
from app.core.utils import utcnow
from app.db import get_session
from app.models import Inventory, Lead, Locality, Society, SocietyInsight, User
from app.schemas.requests import InsightCreate
from app.services.matching import normalize_text

router = APIRouter(tags=["societies"])

HIGH_DEMAND_GAP_THRESHOLD = 3


def _insight_payload(ins: SocietyInsight) -> dict:
    return {
        "id": str(ins.id),
        "note": ins.note,
        "created_by_name": ins.creator.name if ins.creator is not None else None,
        "created_at": ins.created_at,
    }


@router.get("/societies/insights")
async def society_insights(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    societies = (await session.execute(select(Society).order_by(Society.city, Society.name))).scalars().all()
    leads = (await session.execute(apply_lead_scope(select(Lead), user))).scalars().all()
    inventory = (await session.execute(select(Inventory))).scalars().all()
    insights = (
        (await session.execute(select(SocietyInsight).order_by(SocietyInsight.created_at.desc())))
        .scalars()
        .all()
    )

    # demand: a lead counts toward a society if its source society OR Q4 shortlist
    # mentions it — active AND dormant leads alike (Gold Mine reactivates them).
    lead_socs: list[tuple[Lead, set[str]]] = []
    for lead in leads:
        socs: set[str] = set()
        if lead.source_data is not None and lead.source_data.society:
            socs.add(normalize_text(lead.source_data.society))
        for row in lead.shortlist_societies:
            socs.add(normalize_text(row.society))
        lead_socs.append((lead, socs))

    cards = []
    total_demand = 0
    total_live = 0
    high_gaps = 0
    for society in societies:
        key = normalize_text(society.name)
        buyers = [lead for lead, socs in lead_socs if key in socs]
        hot_buyers = [lead for lead in buyers if lead.is_hot]
        live_units = sum(1 for u in inventory if normalize_text(u.society) == key)
        demand_gap = len(buyers) - live_units
        if demand_gap >= HIGH_DEMAND_GAP_THRESHOLD:
            high_gaps += 1
        total_demand += len(buyers)
        total_live += live_units
        cards.append(
            {
                "society": society.name,
                "city": society.city,
                "buyers": len(buyers),
                "hot_buyers": len(hot_buyers),
                "live_units": live_units,
                "demand_gap": demand_gap,
                "insights": [
                    _insight_payload(i) for i in insights if normalize_text(i.society) == key
                ],
            }
        )
    cards.sort(key=lambda c: c["demand_gap"], reverse=True)
    return {
        "stats": {
            "societies_tracked": len(societies),
            "total_demand": total_demand,
            "live_units": total_live,
            "high_demand_gaps": high_gaps,
        },
        "societies": cards,
    }


@router.post("/societies/insights", status_code=201)
async def add_insight(
    payload: InsightCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    insight = SocietyInsight(
        id=uuid.uuid4(),
        society=payload.society.strip(),
        city=payload.city.strip(),
        note=payload.note.strip(),
        created_by=user.id,
        created_at=utcnow(),
    )
    session.add(insight)
    # track the society in the reference list if it's new
    existing = (
        await session.execute(
            select(Society).where(Society.name == insight.society, Society.city == insight.city)
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(Society(name=insight.society, city=insight.city))
    await session.commit()
    insight = (
        await session.execute(
            select(SocietyInsight)
            .where(SocietyInsight.id == insight.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return {
        "id": str(insight.id),
        "society": insight.society,
        "city": insight.city,
        "note": insight.note,
        "created_by_name": insight.creator.name if insight.creator is not None else None,
        "created_at": insight.created_at,
    }


@router.get("/societies")
async def list_societies(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(select(Society).order_by(Society.city, Society.name))).scalars().all()
    return [{"name": s.name, "city": s.city} for s in rows]


@router.get("/localities")
async def list_localities(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(select(Locality).order_by(Locality.city, Locality.name))).scalars().all()
    return [{"name": l.name, "city": l.city} for l in rows]
