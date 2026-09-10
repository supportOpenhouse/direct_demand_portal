"""Sheet → leads, pushed rather than pulled.

The 4-hourly cron PULLS two worksheets with a service account. This is the other
direction: an Apps Script bound to a sheet POSTs its rows here on a trigger.

Why an endpoint at all, rather than the script writing to Neon itself: Apps Script's
JDBC service covers Cloud SQL, MySQL, SQL Server and Oracle — there is no Postgres
driver — so "push straight into the database" is not a thing Apps Script can do. This
is the same shape the Direct Inventory repo's two .gs files already use.

Everything past the token check is the ordinary Meta ingest, so a lead that arrives
this way is indistinguishable from one the cron pulled.
"""
import logging
import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..services.leads_sync import ingest_meta_rows

log = logging.getLogger("sheet_leads")
router = APIRouter(prefix="/sheet-leads", tags=["sheet-leads"])


def _check_token(token: str | None) -> None:
    """Shared-secret gate, same rule as the Huvo webhook.

    Unset is open in dev so local testing needs no setup. In prod that would be an
    unauthenticated public endpoint that inserts leads, so there it refuses to serve
    at all rather than quietly accepting anything.
    """
    secret = (get_settings().SHEET_SYNC_TOKEN or "").strip()
    if not secret:
        if get_settings().is_prod:
            log.error("SHEET_SYNC_TOKEN unset in prod — refusing sheet pushes")
            raise HTTPException(status_code=503,
                                detail="not configured — set SHEET_SYNC_TOKEN")
        return
    # constant-time: a plain == leaks the secret one character at a time to anyone
    # who can measure the response
    if not secrets.compare_digest(token or "", secret):
        raise HTTPException(status_code=403, detail="invalid token")


class SheetPush(BaseModel):
    # Capped so one runaway trigger can't post a whole spreadsheet in a single
    # request; the script batches to match.
    rows: list[dict] = Field(min_length=1, max_length=500)
    actor: str = Field(default="apps-script", max_length=200)


@router.post("/meta")
async def push_meta_rows(
    body: SheetPush,
    x_sync_token: str | None = Header(default=None, alias="X-Sync-Token"),
):
    """Ingest a batch of Meta lead-form rows pushed from a sheet.

    Insert-only and idempotent on `origin_key`, exactly like the cron — re-running the
    trigger over the whole sheet is safe and re-posts cost nothing but the round trip.
    Rows without a phone are skipped rather than rejected: the phone IS the identity,
    and a half-filled form row is normal, not an error worth failing the batch over.
    """
    _check_token(x_sync_token)
    return {"status": "ok", **await ingest_meta_rows(body.rows, body.actor)}
