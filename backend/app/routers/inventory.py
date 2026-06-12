from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db import get_session
from app.models import Inventory, User
from app.services.serializers import unit_payload

router = APIRouter(tags=["inventory"])


@router.get("/inventory")
async def list_inventory(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    units = (
        (await session.execute(select(Inventory).order_by(Inventory.city, Inventory.name))).scalars().all()
    )
    return [unit_payload(u, "inventory") for u in units]
