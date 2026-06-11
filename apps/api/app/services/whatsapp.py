"""WhatsApp provider STUB — the single seam for a future Kaleyra/Interakt/Cloud API
integration. Logs the message and records a lead_activity row; no real sends."""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LeadActivity

log = logging.getLogger("app.whatsapp")


def stub_send(
    session: AsyncSession,
    lead,
    message: str,
    actor_id: uuid.UUID | None = None,
    event: str = "whatsapp_sent",
) -> None:
    log.info("WHATSAPP STUB -> %s (%s): %s", lead.name, lead.phone, message)
    session.add(LeadActivity(lead_id=lead.id, event=event, remark=message, actor_id=actor_id))
