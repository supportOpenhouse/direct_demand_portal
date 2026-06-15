from fastapi import APIRouter, Depends

from ..core.auth import current_user
from ..services.supply import fetch_supply

router = APIRouter(tags=["supply"], dependencies=[Depends(current_user)])


@router.get("/supply")
async def get_supply():
    return await fetch_supply()
