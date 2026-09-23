"""Demand Dashboard — read-only. See services/demand_dashboard.py for the why.

One GET, `current_user` not `require_admin`: the property book is what the whole team
sells from, so everyone who can sign in can read it. There is deliberately NO write
endpoint — not even for an admin. The Demand Dashboard app owns these rows, and two
apps writing the same property with no rule about who wins is how they disagree.
"""
from fastapi import APIRouter, Depends, HTTPException

from ..core.auth import current_user
from ..services.demand_dashboard import fetch_properties

router = APIRouter(tags=["demand-dashboard"], dependencies=[Depends(current_user)])


@router.get("/demand-dashboard")
async def get_demand_dashboard():
    result = await fetch_properties()
    if result["status"] == "not_configured":
        raise HTTPException(status_code=503, detail="properties DB not configured")
    return result
