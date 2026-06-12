from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..db import neon_engine
from ..models import InventoryUnit
from ..services.inventory_sync import read_state, run_sync

router = APIRouter(tags=["inventory"])

# kept in DB, but not exposed to the no-auth frontend
PRIVATE_RAW_KEYS = {"sales_manager_contact"}


@router.get("/inventory")
async def get_inventory():
    state = await read_state()
    engine = neon_engine()
    if engine is None:
        return {
            "status": "not_configured",
            "last_synced_at": None,
            "detail": "Neon not configured — set DATABASE_URL",
            "items": [],
        }
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                select(InventoryUnit.__table__).order_by(InventoryUnit.id)
            )
            items = [
                {
                    "id": u["id"],
                    "name": u["name"],
                    "society": u["society"],
                    "locality": u["locality"],
                    "city": u["city"],
                    "configuration": u["configuration"],
                    "area_sqft": float(u["area_sqft"]) if u["area_sqft"] is not None else None,
                    "price_text": u["price_text"],
                    "price_lacs": float(u["price_lacs"]) if u["price_lacs"] is not None else None,
                    "status": u["status"],
                    "image_url": u["image_url"],
                    "raw": {k: v for k, v in (u["raw"] or {}).items() if k not in PRIVATE_RAW_KEYS},
                }
                for u in res.mappings()
            ]
    except Exception as e:  # table missing / conn error
        return {"status": "error", "last_synced_at": None, "detail": str(e), "items": []}
    status = state.get("last_status") or ("ok" if items else "not_configured")
    return {
        "status": status,
        "last_synced_at": state.get("last_synced_at"),
        "detail": state.get("detail"),
        "items": items,
    }


@router.post("/inventory/sync")
async def sync_inventory():
    result = await run_sync(trigger="manual")
    if result["status"] == "not_configured":
        raise HTTPException(status_code=503, detail=result.get("detail"))
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result.get("detail"))
    state = await read_state()
    return {"status": "ok", "rows": result.get("rows"), "synced_at": state.get("last_synced_at")}
