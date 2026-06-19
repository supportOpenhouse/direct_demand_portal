"""Openhouse Core visit-booking integration (server-to-server, X-CRM-Key).

Per unit, in order (see CRM_VISIT_BOOKING_GUIDE.md):
  1. GET  check-existing-buyer-for-home/  → 45-day lock check + reuse buyer_id
  2. POST buyer/                          → only if step 1 returned no buyer_id
  3. POST crm/schedule-visits/            → all ready visits in one call (1–10)

Partial success is normal: each unit's result is independent. The CRM_API_KEY is
never logged or returned; mobile numbers are masked in logs.
"""
import logging
import re

import httpx

from ..config import get_settings
from .normalize import normalize_city

log = logging.getLogger("crm_booking")

# city → (Openhouse Broker.id used as the CP, display label). Gurgaon books under
# CP 708; Noida & Ghaziabad under CP 1367.
BROKER_BY_CITY: dict[str, tuple[int, str]] = {
    "Gurgaon": (708, "Gurgaon"),
    "Noida": (1367, "Noida"),
    "Ghaziabad": (1367, "Ghaziabad"),
}
DEFAULT_SOURCE = "direct"
SLOT_VALUES = ["9-11 AM", "11-1 PM", "1-3 PM", "3-5 PM", "5-7 PM", "7-9 PM"]


def broker_for_city(city: str | None) -> tuple[int, str] | None:
    """(broker_id, label) for a unit's city, or None if no CP is configured for it."""
    return BROKER_BY_CITY.get(normalize_city(city) or "")


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _mask(mobile: str) -> str:
    d = _digits(mobile)
    return ("•" * max(0, len(d) - 2)) + d[-2:] if d else "—"


def _client() -> httpx.AsyncClient:
    s = get_settings()
    base = s.CRM_BOOKING_API_BASE_URL.rstrip("/") + "/"  # must end in /api/v1/oh/
    return httpx.AsyncClient(base_url=base, headers={"X-CRM-Key": s.CRM_API_KEY}, timeout=25.0)


def _err_text(r: httpx.Response) -> str:
    """Human-readable message from a non-2xx Core response."""
    try:
        b = r.json()
        if isinstance(b, dict):
            return str(b.get("error") or b.get("detail") or b.get("message") or f"HTTP {r.status_code}")
    except Exception:  # noqa: BLE001
        pass
    return f"HTTP {r.status_code}"


async def _check_buyer(client: httpx.AsyncClient, home_id: int, last5: str, name: str) -> dict:
    """Step 1. Returns {status: ok|error, locked?, buyer_id?, message?, remaining_days?}."""
    try:
        r = await client.get(
            "check-existing-buyer-for-home/",
            params={"home_id": home_id, "last_five_digits": last5, "name": name},
        )
    except httpx.HTTPError as e:
        log.warning("check-buyer home=%s mob=%s NETWORK %s", home_id, _mask(last5), e)
        return {"status": "error", "detail": "Couldn't reach the booking service"}
    log.info("check-buyer home=%s mob=%s name=%s -> %s", home_id, _mask(last5), name, r.status_code)
    if r.status_code == 404:
        return {"status": "error", "detail": "Home not found"}
    if r.status_code == 401:
        return {"status": "error", "detail": "Booking key rejected by Core"}
    if r.status_code == 503:
        return {"status": "error", "detail": "Booking not enabled on Core"}
    if r.status_code >= 400:
        return {"status": "error", "detail": _err_text(r)}
    data = r.json()
    if data.get("exists"):  # locked with another CP
        return {
            "status": "ok", "locked": True,
            "message": data.get("message") or "Buyer is registered with another CP",
            "remaining_days": data.get("remainingDays"),
        }
    return {"status": "ok", "locked": False, "buyer_id": data.get("buyerId")}


async def _create_buyer(client: httpx.AsyncClient, smid: int, name: str, mobile: str, broker_id: int) -> dict:
    """Step 2. Returns {status, buyer_id?|detail}."""
    try:
        r = await client.post("buyer/", json={
            "sales_manager_id": smid, "name": name, "mobile_number": mobile,
            "broker_id": broker_id, "profession": "",
        })
    except httpx.HTTPError as e:
        log.warning("create-buyer mob=%s NETWORK %s", _mask(mobile), e)
        return {"status": "error", "detail": "Couldn't reach the booking service"}
    log.info("create-buyer name=%s mob=%s broker=%s -> %s", name, _mask(mobile), broker_id, r.status_code)
    if r.status_code in (200, 201):
        return {"status": "ok", "buyer_id": r.json().get("id")}
    if r.status_code == 422:
        return {"status": "error", "detail": "Your Openhouse SMID is not valid"}
    return {"status": "error", "detail": _err_text(r)}


async def _schedule(client: httpx.AsyncClient, smid: int, visits: list[dict]) -> dict:
    """Step 3. Returns {status, data?|detail} where data has results[]."""
    try:
        r = await client.post("crm/schedule-visits/", json={"sales_manager_id": smid, "visits": visits})
    except httpx.HTTPError as e:
        log.warning("schedule NETWORK %s", e)
        return {"status": "error", "detail": "Couldn't reach the booking service"}
    log.info("schedule sm=%s n=%s -> %s", smid, len(visits), r.status_code)
    if r.status_code == 422:
        return {"status": "error", "detail": "Your Openhouse SMID is not valid"}
    if r.status_code >= 400:
        return {"status": "error", "detail": _err_text(r)}
    return {"status": "ok", "data": r.json()}


async def book_visits(smid: int, selected_date: str, selected_time: str, source: str, units: list[dict]) -> list[dict]:
    """Orchestrate the full per-unit flow. `units` = [{home_id, city, buyer_name, buyer_mobile}].
    Returns one result per unit: {home_id, ok, visit_id?, error?, remaining_days?}. Never raises."""
    results: dict[int, dict] = {}
    ready: list[dict] = []  # visits that cleared steps 1–2, for the batch schedule
    async with _client() as client:
        for u in units:
            home_id = u["home_id"]
            name = (u.get("buyer_name") or "").strip()
            mobile = _digits(u.get("buyer_mobile"))
            last5 = mobile[-5:]
            broker = broker_for_city(u.get("city"))
            if broker is None:
                results[home_id] = {"home_id": home_id, "ok": False, "error": f"No CP configured for {u.get('city') or 'this city'}"}
                continue
            broker_id, _label = broker

            chk = await _check_buyer(client, home_id, last5, name)
            if chk["status"] == "error":
                results[home_id] = {"home_id": home_id, "ok": False, "error": chk["detail"]}
                continue
            if chk.get("locked"):
                results[home_id] = {"home_id": home_id, "ok": False, "error": chk["message"], "remaining_days": chk.get("remaining_days")}
                continue

            buyer_id = chk.get("buyer_id")
            if not buyer_id:
                made = await _create_buyer(client, smid, name, mobile, broker_id)
                if made["status"] == "error":
                    results[home_id] = {"home_id": home_id, "ok": False, "error": made["detail"]}
                    continue
                buyer_id = made["buyer_id"]

            ready.append({
                "buyer_id": buyer_id, "broker_id": broker_id, "home_id": home_id,
                "selected_date": selected_date, "selected_time": selected_time, "source": source,
            })

        if ready:
            sched = await _schedule(client, smid, ready)
            if sched["status"] == "error":  # whole-batch failure → mark all ready as failed
                for v in ready:
                    results[v["home_id"]] = {"home_id": v["home_id"], "ok": False, "error": sched["detail"]}
            else:
                for item in sched["data"].get("results", []):
                    hid = item.get("homeId")
                    if item.get("ok"):
                        results[hid] = {"home_id": hid, "ok": True, "visit_id": (item.get("visit") or {}).get("id")}
                    else:
                        results[hid] = {"home_id": hid, "ok": False, "error": item.get("error") or "Booking failed"}
                # any ready unit the API didn't echo back
                for v in ready:
                    results.setdefault(v["home_id"], {"home_id": v["home_id"], "ok": False, "error": "No response from booking service"})

    # preserve the input order
    return [results[u["home_id"]] for u in units if u["home_id"] in results]
