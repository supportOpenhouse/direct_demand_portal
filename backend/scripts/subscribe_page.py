"""One-time: subscribe the app to the Openhouse Page's `leadgen` field.

Run AFTER the webhook is deployed and "Verify and Save" has gone green in the app
dashboard. Subscribing a Page whose callback URL is not yet verified is accepted and
then delivers nothing, which looks exactly like a broken endpoint.

    cd backend && uv run python scripts/subscribe_page.py

Re-runnable: subscribing twice is a no-op on Meta's side. Reads META_ACCESS_TOKEN and
META_PAGE_ID from the environment / ../.env like the app does.

Note the two-step. The system-user token cannot subscribe a Page — that call needs a
PAGE token, which the first request exchanges it for.
"""
import asyncio
import sys

import httpx

from app.config import get_settings


async def main() -> int:
    settings = get_settings()
    page_id = (settings.META_PAGE_ID or "").strip()
    token = (settings.META_ACCESS_TOKEN or "").strip()
    if not page_id or not token:
        print("set META_PAGE_ID and META_ACCESS_TOKEN first")
        return 2

    base = settings.meta_graph_base
    print(f"graph: {base}  page: {page_id}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{base}/{page_id}",
            params={"fields": "name,access_token", "access_token": token},
        )
        resp.raise_for_status()
        page = resp.json()
        page_token = page["access_token"]
        print(f"page token acquired for {page.get('name')!r}")

        resp = await client.post(
            f"{base}/{page_id}/subscribed_apps",
            params={"subscribed_fields": "leadgen", "access_token": page_token},
        )
        resp.raise_for_status()
        print("subscribe:", resp.json())

        # Ground truth, and the only thing worth trusting over any settings screen.
        resp = await client.get(
            f"{base}/{page_id}/subscribed_apps", params={"access_token": page_token}
        )
        resp.raise_for_status()
        print("subscribed apps now:", resp.json())
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
