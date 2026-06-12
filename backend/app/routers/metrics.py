from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db import get_session
from app.models import User
from app.services.metrics import dashboard_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics/dashboard")
async def metrics_dashboard(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await dashboard_metrics(session, user)
