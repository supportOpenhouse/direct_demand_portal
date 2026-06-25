"""Admin audit-log API — backs the Logs page."""
from fastapi import APIRouter, Depends, Query

from ..core.auth import require_admin
from ..services.audit import list_actors, query_logs

router = APIRouter(tags=["logs"], dependencies=[Depends(require_admin)])


@router.get("/logs")
async def get_logs(
    actor: str | None = Query(None),
    category: str | None = Query(None),       # auth | write | read
    method: str | None = Query(None),
    q: str | None = Query(None),              # search action/path/actor
    status: int | None = Query(None),
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await query_logs(
        actor=actor, category=category, method=method, q=q, status=status,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )


@router.get("/logs/actors")
async def get_actors():
    """Distinct actor emails — for the Logs page filter dropdown."""
    return {"items": await list_actors()}
