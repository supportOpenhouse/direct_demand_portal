"""External analytics — served at /v1/huvoa-nalytics.

Scaffold for a page that doesn't exist yet. No provider is wired up, so this answers
`not_configured` rather than failing: the frontend can be built against a real
contract today, and when a source appears only the body changes.

The shape is /v1/inventory's and /v1/supply's — {status, detail, items} — because
those already taught the frontend to tell "configured but empty" apart from "not set
up yet", and a third convention would only be a third thing to learn.

Module named for what it is; the route keeps the name it was asked for. Python module
names can't hold a hyphen anyway.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..config import get_settings
from ..core.auth import current_user

log = logging.getLogger("external_analytics")

# Signed-in users, not admin-only: this is a reporting view of work the whole team
# does. Tighten it here if the provider ever returns something commercially sensitive.
router = APIRouter(tags=["analytics"])

# The one setting that would light this up. Named in the response so an unconfigured
# deploy tells you what's missing instead of just showing an empty page.
PROVIDER_ENV = "HUVO_ANALYTICS_URL"


@router.get("/huvoa-nalytics")
async def external_analytics(_: dict = Depends(current_user)) -> dict:
    """Analytics from the external provider.

    Returns `not_configured` until PROVIDER_ENV is set. Deliberately never raises —
    a reporting page that 500s is worse than one that says it isn't switched on.
    """
    configured = bool(getattr(get_settings(), PROVIDER_ENV, ""))
    now = datetime.now(timezone.utc).isoformat()

    if not configured:
        return {
            "status": "not_configured",
            "detail": f"External analytics isn't set up — set {PROVIDER_ENV}",
            "items": [],
            "generated_at": now,
        }

    # No provider client yet. Reaching here means someone set the env var ahead of the
    # integration, so say so plainly rather than returning a silent empty list that
    # reads as "the provider has no data".
    log.warning("%s is set but no provider client is implemented yet", PROVIDER_ENV)
    return {
        "status": "not_implemented",
        "detail": f"{PROVIDER_ENV} is set, but the provider client hasn't been built yet",
        "items": [],
        "generated_at": now,
    }
