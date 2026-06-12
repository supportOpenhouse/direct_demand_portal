from fastapi import APIRouter

from ..services.supply import fetch_supply

router = APIRouter(tags=["supply"])


@router.get("/supply")
async def get_supply():
    return await fetch_supply()
