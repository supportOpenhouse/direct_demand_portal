import uuid
from datetime import timedelta

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import apply_lead_scope, get_current_user, require_roles
from app.core.errors import ApiError
from app.core.utils import utcnow
from app.db import get_session
from app.models import (
    Interest,
    Inventory,
    Lead,
    LeadActivity,
    LeadConfirmedData,
    LeadPreferredLocality,
    LeadShortlistSociety,
    LeadSourceData,
    SupplyUnit,
    User,
)
from app.schemas.requests import (
    ConfirmRequest,
    HotRequest,
    IngestLeadRequest,
    Segment,
    SourceDataPatch,
    StageRequest,
)
from app.services import whatsapp
from app.services.matching import build_lead_profile, match_pct, top_matches
from app.services.segments import segment_criteria
from app.services.serializers import lead_detail, lead_row, unit_payload
from app.services.tat import tat_deadline_for, tat_minutes_for_source

router = APIRouter(tags=["leads"])


async def fetch_lead(session: AsyncSession, lead_id: uuid.UUID, user: User | None = None) -> Lead:
    """Scoped fetch; refreshes any already-tracked instance (populate_existing)."""
    stmt = select(Lead).where(Lead.id == lead_id).execution_options(populate_existing=True)
    if user is not None:
        stmt = apply_lead_scope(stmt, user)
    lead = (await session.execute(stmt)).scalar_one_or_none()
    if lead is None:
        raise ApiError(404, "Lead not found")
    return lead


@router.get("/leads")
async def list_leads(
    segment: Segment | None = None,
    assigned_to: uuid.UUID | None = None,
    city: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    now = utcnow()
    stmt = apply_lead_scope(select(Lead), user)
    if segment is not None:
        stmt = stmt.where(*segment_criteria(segment, now))
    if assigned_to is not None:
        stmt = stmt.where(Lead.assigned_to == assigned_to)
    if city:
        stmt = stmt.where(func.lower(Lead.city) == city.strip().lower())
    stmt = stmt.order_by(Lead.created_at.desc())
    leads = (await session.execute(stmt)).scalars().all()
    items = [lead_row(l, now) for l in leads]
    return {"items": items, "count": len(items)}


@router.get("/leads/{lead_id}")
async def get_lead(
    lead_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lead = await fetch_lead(session, lead_id, user)
    return lead_detail(lead, utcnow())


@router.post("/leads/ingest", status_code=201)
async def ingest_lead(
    payload: IngestLeadRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    now = utcnow()

    # Round-robin-ish assignment: active RM currently carrying the fewest leads.
    rm_stmt = (
        select(User, func.count(Lead.id).label("lead_count"))
        .outerjoin(Lead, Lead.assigned_to == User.id)
        .where(User.role == "rm", User.active.is_(True))
        .group_by(User.id)
        .order_by(sa.text("lead_count ASC"), User.created_at.asc())
    )
    rm_row = (await session.execute(rm_stmt)).first()
    rm = rm_row[0] if rm_row is not None else None

    minutes = await tat_minutes_for_source(session, payload.source)
    lead = Lead(
        id=uuid.uuid4(),
        name=payload.name,
        phone=payload.phone,
        source=payload.source,
        assigned_to=rm.id if rm is not None else None,
        stage="new",
        tat_deadline=tat_deadline_for(now, minutes),
        confirmed=False,
        is_hot=payload.plan_to_buy == "within_30_days",
        city=payload.city,
        created_at=now,
    )
    session.add(lead)
    session.add(
        LeadSourceData(
            lead_id=lead.id,
            budget_band=payload.budget_band,
            budget_min_lacs=payload.budget_min_lacs,
            budget_max_lacs=payload.budget_max_lacs,
            city=payload.city,
            society=payload.society,
            configuration=payload.configuration,
            plan_to_buy=payload.plan_to_buy,
        )
    )
    session.add(
        LeadActivity(
            lead_id=lead.id,
            event="lead_ingested",
            remark=f"Lead captured from {payload.source}"
            + (f", assigned to {rm.name}" if rm is not None else ""),
        )
    )
    whatsapp.stub_send(
        session,
        lead,
        f"New lead alert: {payload.name} ({payload.city or 'NCR'})"
        + (f" -> {rm.name}" if rm is not None else ""),
        event="whatsapp_alert",
    )
    await session.commit()
    lead = await fetch_lead(session, lead.id)
    return lead_row(lead, utcnow())


@router.patch("/leads/{lead_id}/source-data")
async def patch_source_data(
    lead_id: uuid.UUID,
    payload: SourceDataPatch,
    user: User = Depends(require_roles("admin")),  # 403 unless Admin — hard rule
    session: AsyncSession = Depends(get_session),
):
    lead = await fetch_lead(session, lead_id, user)
    src = lead.source_data
    if src is None:
        src = LeadSourceData(lead_id=lead.id)
        session.add(src)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(src, field, value)
    if "city" in changes:
        lead.city = changes["city"]  # keep the denormalized city in sync
    if changes:
        session.add(
            LeadActivity(
                lead_id=lead.id,
                event="source_data_updated",
                remark=f"Updated: {', '.join(sorted(changes))}",
                actor_id=user.id,
            )
        )
    await session.commit()
    lead = await fetch_lead(session, lead_id)
    return lead_detail(lead, utcnow())


@router.post("/leads/{lead_id}/confirm")
async def confirm_lead(
    lead_id: uuid.UUID,
    payload: ConfirmRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lead = await fetch_lead(session, lead_id, user)

    # §6.6 mandatory fields — report EVERY missing field at once
    missing: dict[str, str] = {}
    if payload.purpose is None:
        missing["purpose"] = "Q1 Purpose is required"
    if payload.budget_value_lacs is None:
        missing["budget_value_lacs"] = "Q2 Budget is required"
    elif payload.budget_value_lacs <= 0:
        missing["budget_value_lacs"] = "Q2 Budget must be a positive ₹ value (in lacs)"
    if not (payload.configuration or "").strip():
        missing["configuration"] = "Q3 Configuration is required"
    if payload.office_willing is None:
        missing["office_willing"] = "Q6 Office-visit willingness is required"
    if missing:
        raise ApiError(422, "Missing mandatory fields", missing)

    now = utcnow()
    conf = lead.confirmed_data
    if conf is None:
        conf = LeadConfirmedData(lead_id=lead.id)
        session.add(conf)
    conf.purpose = payload.purpose
    conf.budget_value_lacs = payload.budget_value_lacs
    conf.configuration = payload.configuration.strip()
    conf.office_willing = payload.office_willing
    conf.office_preferred_date = payload.office_preferred_date
    conf.remark = payload.remark
    conf.confirmed_at = now

    # replace Q4/Q5 rows
    await session.execute(
        sa.delete(LeadShortlistSociety).where(LeadShortlistSociety.lead_id == lead.id)
    )
    await session.execute(
        sa.delete(LeadPreferredLocality).where(LeadPreferredLocality.lead_id == lead.id)
    )
    for society in dict.fromkeys(s.strip() for s in payload.shortlist_societies if s.strip()):
        session.add(LeadShortlistSociety(lead_id=lead.id, society=society))
    for locality in dict.fromkeys(l.strip() for l in payload.preferred_localities if l.strip()):
        session.add(LeadPreferredLocality(lead_id=lead.id, locality=locality))

    lead.confirmed = True
    lead.qualified_at = now
    if lead.stage == "new":
        lead.stage = "contacted"
    lead.tat_deadline = None  # TAT cleared on first confirm
    if lead.source_data is not None and lead.source_data.plan_to_buy == "within_30_days":
        lead.is_hot = True

    session.add(
        LeadActivity(
            lead_id=lead.id,
            event="confirmed",
            remark=payload.remark or "Lead confirmed & qualified on call (Q1–Q6)",
            actor_id=user.id,
        )
    )
    await session.commit()
    lead = await fetch_lead(session, lead_id)
    return lead_detail(lead, utcnow())


@router.post("/leads/{lead_id}/stage")
async def change_stage(
    lead_id: uuid.UUID,
    payload: StageRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not (payload.remark or "").strip():
        raise ApiError(422, "Validation error", {"remark": "A remark is required for stage changes"})
    lead = await fetch_lead(session, lead_id, user)
    from_stage = lead.stage
    lead.stage = payload.to_stage
    # qualified bookkeeping: qualified_at is preserved as-is (won keeps it)
    session.add(
        LeadActivity(
            lead_id=lead.id,
            event="stage_changed",
            remark=f"{from_stage} → {payload.to_stage}: {payload.remark.strip()}",
            actor_id=user.id,
        )
    )
    await session.commit()
    lead = await fetch_lead(session, lead_id)
    return lead_detail(lead, utcnow())


@router.post("/leads/{lead_id}/hot")
async def toggle_hot(
    lead_id: uuid.UUID,
    payload: HotRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lead = await fetch_lead(session, lead_id, user)
    lead.is_hot = payload.is_hot
    session.add(
        LeadActivity(
            lead_id=lead.id,
            event="hot_toggled",
            remark="Marked as immediate buyer 🔥" if payload.is_hot else "Hot flag removed",
            actor_id=user.id,
        )
    )
    await session.commit()
    lead = await fetch_lead(session, lead_id)
    return lead_row(lead, utcnow())


async def _match_payload(session, lead, model, kind: str) -> list[dict]:
    profile = build_lead_profile(lead)
    stmt = select(model)
    if profile.city:
        stmt = stmt.where(func.lower(model.city) == profile.city)  # city = HARD filter in SQL
    units = (await session.execute(stmt)).scalars().all()

    interest_counts: dict = {}
    if kind == "supply":
        rows = await session.execute(
            select(Interest.supply_unit_id, func.count()).group_by(Interest.supply_unit_id)
        )
        interest_counts = dict(rows.all())

    return [
        {
            "unit": unit_payload(u, kind, interest_counts.get(u.id, 0)),
            "score": score,
            "match_pct": match_pct(score),
            "matched_on": matched_on,
        }
        for (u, score, matched_on) in top_matches(profile, units, limit=5)
    ]


@router.get("/leads/{lead_id}/matches/inventory")
async def lead_matches_inventory(
    lead_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lead = await fetch_lead(session, lead_id, user)
    return await _match_payload(session, lead, Inventory, "inventory")


@router.get("/leads/{lead_id}/matches/supply")
async def lead_matches_supply(
    lead_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lead = await fetch_lead(session, lead_id, user)
    return await _match_payload(session, lead, SupplyUnit, "supply")
