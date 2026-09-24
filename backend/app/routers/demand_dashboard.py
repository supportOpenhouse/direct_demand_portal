"""Demand Dashboard — read-only. See services/demand_dashboard.py for the why.

One GET, `current_user` not `require_admin`: the property book is what the whole team
sells from, so everyone who can sign in can read it. There is deliberately NO write
endpoint — not even for an admin. The Demand Dashboard app owns these rows, and two
apps writing the same property with no rule about who wins is how they disagree.
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ..config import get_settings
from ..core.auth import current_user
from ..services.demand_dashboard import fetch_properties

router = APIRouter(tags=["demand-dashboard"], dependencies=[Depends(current_user)])


@router.get("/demand-dashboard")
async def get_demand_dashboard():
    result = await fetch_properties()
    if result["status"] == "not_configured":
        raise HTTPException(status_code=503, detail="properties DB not configured")
    return result


@router.get("/demand-dashboard/brochure/{home_id}")
async def get_brochure(home_id: int):
    """The home's brochure PDF from Openhouse Core — a link to open, not the file.

    `home_id` is the property's `core_home_id`. A property without one has no brochure;
    the page says "No home id" and never calls this. Still a GET, still no write on our
    side (Core caches the PDF it renders, which is its own business)."""
    if not get_settings().crm_booking_configured:
        raise HTTPException(status_code=503, detail="Openhouse Core isn't configured (CRM_API_KEY).")
    from ..services.crm_booking import fetch_brochure

    res = await fetch_brochure(home_id)
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail=res["detail"])
    if res["status"] == "error":
        raise HTTPException(status_code=502, detail=res["detail"])
    return {"url": res["url"], "filename": res["filename"]}


@router.get("/demand-dashboard/brochure/{home_id}/file")
async def download_brochure_file(home_id: int):
    """The brochure PDF itself, as an attachment — the table's download button. See
    `crm_booking.download_brochure` for why the server fetches it rather than the page."""
    if not get_settings().crm_booking_configured:
        raise HTTPException(status_code=503, detail="Openhouse Core isn't configured (CRM_API_KEY).")
    from ..services.crm_booking import download_brochure

    res = await download_brochure(home_id)
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail=res["detail"])
    if res["status"] == "error":
        raise HTTPException(status_code=502, detail=res["detail"])
    # filename* keeps a name with spaces or non-ASCII intact; the plain one is for old clients
    name = res["filename"]
    return Response(res["content"], media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=\"brochure-{home_id}.pdf\"; filename*=UTF-8''{quote(name)}"})
