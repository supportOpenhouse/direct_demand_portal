from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.auth import current_user
from ..services.matching import invalidate_units_cache
from ..services.supply import fetch_supply, set_priority

router = APIRouter(tags=["supply"], dependencies=[Depends(current_user)])


@router.get("/supply")
async def get_supply():
    return await fetch_supply()


class PriorityPayload(BaseModel):
    priority: bool = True


@router.post("/supply/{uid}/priority")
async def mark_priority(uid: str, payload: PriorityPayload):
    """Set/unset the Direct Demand priority flag on a supply unit (external DB)."""
    result = await set_priority(uid, payload.priority)
    if result["status"] == "ok":
        await invalidate_units_cache()  # so the next lead-match reflects it immediately (all instances)
        return result
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="property not found")
    if result["status"] == "not_configured":
        raise HTTPException(status_code=503, detail="properties DB not configured")
    raise HTTPException(status_code=502, detail=result.get("detail", "could not update priority"))
