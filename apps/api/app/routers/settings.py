from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.core.errors import ApiError
from app.db import get_session
from app.models import ApiKey, SettingsIntegration
from app.schemas.requests import AssignmentPatch, IntegrationPatch

router = APIRouter(tags=["settings"], dependencies=[Depends(require_roles("admin"))])

# canonical no-code integrations + display labels (label may be overridden in row.value)
INTEGRATIONS: list[tuple[str, str]] = [
    ("meta", "Meta Lead Ads"),
    ("gads", "Google Ads"),
    ("99acres", "99acres"),
    ("magicbricks", "MagicBricks"),
    ("youtube", "YouTube"),
    ("whatsapp", "WhatsApp Cloud API"),
    ("sheets", "Google Sheets"),
]
INTEGRATION_KEYS = {k for k, _ in INTEGRATIONS}
DEFAULT_WEBHOOK_URL = "https://api.openhouse.in/v1/leads/ingest"


async def _settings_payload(session: AsyncSession) -> dict:
    rows = {
        r.key: r
        for r in (await session.execute(select(SettingsIntegration))).scalars().all()
    }
    integrations = []
    for key, label in INTEGRATIONS:
        row = rows.get(key)
        row_label = (row.value or {}).get("label") if row is not None and isinstance(row.value, dict) else None
        integrations.append(
            {"key": key, "label": row_label or label, "enabled": bool(row.enabled) if row else False}
        )

    api_key = (
        await session.execute(
            select(ApiKey).where(ApiKey.revoked.is_(False)).order_by(ApiKey.created_at.asc())
        )
    ).scalars().first()
    api_key_masked = f"oh_live_••••••••{api_key.hash[-4:]}" if api_key is not None else ""

    webhook_row = rows.get("webhook_url")
    webhook_url = (
        (webhook_row.value or {}).get("url")
        if webhook_row is not None and isinstance(webhook_row.value, dict)
        else None
    ) or DEFAULT_WEBHOOK_URL

    assignment_row = rows.get("assignment")
    assignment_method = (
        (assignment_row.value or {}).get("method")
        if assignment_row is not None and isinstance(assignment_row.value, dict)
        else None
    ) or "round_robin"

    return {
        "integrations": integrations,
        "api_key_masked": api_key_masked,
        "webhook_url": webhook_url,
        "assignment_method": assignment_method,
    }


@router.get("/settings")
async def get_settings(session: AsyncSession = Depends(get_session)):
    return await _settings_payload(session)


@router.patch("/settings/integrations")
async def patch_integration(payload: IntegrationPatch, session: AsyncSession = Depends(get_session)):
    if payload.key not in INTEGRATION_KEYS:
        raise ApiError(422, "Validation error", {"key": "Unknown integration key"})
    row = await session.get(SettingsIntegration, payload.key)
    if row is None:
        row = SettingsIntegration(key=payload.key, value={"label": dict(INTEGRATIONS)[payload.key]})
        session.add(row)
    row.enabled = payload.enabled
    await session.commit()
    return await _settings_payload(session)


@router.patch("/settings/assignment")
async def patch_assignment(payload: AssignmentPatch, session: AsyncSession = Depends(get_session)):
    row = await session.get(SettingsIntegration, "assignment")
    if row is None:
        row = SettingsIntegration(key="assignment", enabled=True)
        session.add(row)
    row.value = {"method": payload.method}
    await session.commit()
    return await _settings_payload(session)
