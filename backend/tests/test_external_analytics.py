"""The external-analytics endpoint.

A scaffold: the page it feeds doesn't exist yet and no provider is wired up. What it
does have is a settled contract, so the frontend can be built against it today and
only the body has to change when a real source appears.

The shape mirrors /v1/inventory and /v1/supply — {status, detail, items} — because
those already taught the frontend how to render "configured but empty" differently
from "not set up yet", and a third convention would just be a third thing to learn.
"""
from app.routers.external_analytics import PROVIDER_ENV, router


def test_it_answers_on_the_agreed_path():
    """External consumers pin URLs, so the path is part of the contract."""
    paths = {r.path for r in router.routes}
    assert "/huvo-analytics" in paths


async def test_it_reports_not_configured_rather_than_failing():
    """No provider is wired up yet. An endpoint that 500s can't be built against;
    one that says 'not_configured' can — same as inventory and supply do."""
    from app.routers.external_analytics import external_analytics

    body = await external_analytics({"email": "a@x.in", "role": "rm"})

    assert body["status"] == "not_configured"
    assert body["items"] == []
    # names the env var that would light it up, so the answer is actionable
    assert PROVIDER_ENV in body["detail"]


async def test_the_payload_always_carries_the_keys_the_page_reads():
    """The frontend indexes straight into these. A key that only appears in the happy
    path is a crash on the unhappy one."""
    from app.routers.external_analytics import external_analytics

    body = await external_analytics({"email": "a@x.in", "role": "rm"})

    assert set(body) == {"status", "detail", "items", "generated_at"}


async def test_generated_at_is_iso_utc():
    """Timestamps in this app are ISO-8601 UTC everywhere; the page will format it."""
    from datetime import datetime

    from app.routers.external_analytics import external_analytics

    body = await external_analytics({"email": "a@x.in", "role": "rm"})
    parsed = datetime.fromisoformat(body["generated_at"])

    assert parsed.tzinfo is not None
