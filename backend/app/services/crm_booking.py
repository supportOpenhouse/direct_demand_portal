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
# ⚠️ Core stores selected_time as FREE TEXT and its duplicate-slot check is a plain string
# compare, so "3-5 PM" and "3 - 5 PM" are two different slots to it. Prod carries both
# (297 rows unspaced from our own booking, 75 spaced from the Openhouse app). These are
# the SPACED forms the app and the API guide use — mirror in frontend/src/lib/slots.ts.
SLOT_VALUES = ["9 - 11 AM", "11 - 1 PM", "1 - 3 PM", "3 - 5 PM", "5 - 7 PM", "7 - 9 PM"]

# One canonical spelling, accepted in any of the spellings that exist in the wild.
#
# "3-5 PM" and "3 - 5 PM" are the same slot to a person and two different slots to Core,
# which compares them as strings. Both forms are already out there: 297 prod visits were
# booked unspaced by our own older builds, a deployed frontend can lag a backend deploy by
# hours, and the Openhouse app writes the spaced one. Rejecting a spelling we understand
# perfectly well just breaks booking for whoever is behind — so every entry point
# normalises to SLOT_VALUES instead, and only a slot we genuinely don't recognise is a 400.
def _slot_key(v: str) -> str:
    return "".join(v.split()).upper()


_SLOT_BY_KEY = {_slot_key(v): v for v in SLOT_VALUES}
# …and by the hours alone, so a bare "3-5" resolves too. The six slots have distinct hour
# pairs (9-11, 11-1, 1-3, 3-5, 5-7, 7-9), so dropping AM/PM loses nothing — asserted here
# rather than assumed, because adding a 7th slot could break it silently.
_HOURS_ONLY = {_slot_key(v.rsplit(" ", 1)[0]): v for v in SLOT_VALUES}
assert len(_HOURS_ONLY) == len(SLOT_VALUES), "two slots share the same hours — drop the bare-hours form"


def canonical_slot(raw: str | None) -> str | None:
    """The canonical spaced slot for any accepted spelling, or None if it isn't a slot.

    Accepts "3 - 5 PM", "3-5 PM", "3 -5 pm" and "3-5" — all the same slot to a person."""
    key = _slot_key(raw or "")
    return _SLOT_BY_KEY.get(key) or _HOURS_ONLY.get(key)


# PUT /schedule-visits/{id}/ — the completion/cancellation contract.
LEAD_STATUS_VALUES = ["hot", "warm", "cold", "future_prospect", "dead", "select_status"]
# the six keys of sm_demand_feedback, in the order the form asks them
SM_FEEDBACK_FIELDS = [
    "time_spent_on_site", "society_amenity_tour", "price_discussion",
    "client_queries", "closing_signal", "buyer_primary_concern",
]


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


# --- single-visit operations (manage visits) -------------------------------------
# Four Core calls, one visit at a time. Each returns {status: ok|error, visit?|detail}
# and never raises, matching book_visits' contract.
#
# ⚠️ PUT /schedule-visits/{id}/ WRITES selected_date/selected_time — it does not check
# them. Cancelling visit 7595 with selected_date="1999-01-01" moved the visit to 1999
# (verified on staging). So complete/cancel must echo the visit's CURRENT stored slot
# back verbatim, never a normalised or remembered one — which is why both read the visit
# first instead of trusting what the caller passed in.


async def fetch_visit(visit_id: int) -> dict:
    """The visit as Core holds it right now. {status, visit?|detail}."""
    async with _client() as client:
        return await _fetch_visit(client, visit_id)


async def _fetch_visit(client: httpx.AsyncClient, visit_id: int) -> dict:
    try:
        r = await client.get("crm/visits/", params={"ids": str(visit_id)})
    except httpx.HTTPError as e:
        log.warning("fetch-visit %s NETWORK %s", visit_id, e)
        return {"status": "error", "detail": "Couldn't reach the booking service"}
    if r.status_code >= 400:
        return {"status": "error", "detail": _err_text(r)}
    visits = r.json().get("visits") or []
    if not visits:
        return {"status": "error", "detail": f"Visit {visit_id} not found on Openhouse"}
    return {"status": "ok", "visit": visits[0]}


async def _put_status(visit_id: int, status: str, extra: dict | None = None) -> dict:
    """Complete or cancel, echoing the visit's own date/time back. {status, visit?|detail}."""
    async with _client() as client:
        got = await _fetch_visit(client, visit_id)
        if got["status"] == "error":
            return got
        v = got["visit"]
        body = {
            "selected_date": v.get("selectedDate"),
            "selected_time": v.get("selectedTime"),
            "status": status,
            **(extra or {}),
        }
        try:
            r = await client.put(f"schedule-visits/{visit_id}/", json=body)
        except httpx.HTTPError as e:
            log.warning("%s visit=%s NETWORK %s", status, visit_id, e)
            return {"status": "error", "detail": "Couldn't reach the booking service"}
    log.info("%s visit=%s -> %s", status, visit_id, r.status_code)
    if r.status_code >= 400:
        return {"status": "error", "detail": _err_text(r)}
    return {"status": "ok", "visit": r.json()}


async def cancel_visit(visit_id: int) -> dict:
    """Cancel an upcoming visit. Core stamps platform='crm'."""
    return await _put_status(visit_id, "cancelled")


async def complete_visit(
    visit_id: int,
    sales_feedback: str,
    lead_status: str | None = None,
    sm_feedback: dict | None = None,
) -> dict:
    """Mark a visit completed. With lead_status + sm_feedback this is the ASSISTED path
    (the SM filled the form); with sales_feedback alone it's the OTP path. Core picks the
    path from the payload, so the keys are omitted entirely rather than sent as null."""
    extra: dict = {"sales_feedback": sales_feedback}
    if lead_status:
        extra["lead_status"] = lead_status
    clean = {k: v for k, v in (sm_feedback or {}).items() if k in SM_FEEDBACK_FIELDS and v}
    if clean:
        extra["sm_demand_feedback"] = clean
    return await _put_status(visit_id, "completed", extra)


async def reschedule_visit(visit_id: int, selected_date: str, selected_time: str) -> dict:
    """Move an UPCOMING visit to a new slot. Same visit id; SM unchanged."""
    return await _post_slot("crm/reschedule-visits/", visit_id, selected_date, selected_time)


async def create_revisit(visit_id: int, selected_date: str, selected_time: str) -> dict:
    """Clone a COMPLETED visit into a new upcoming one — same buyer, same home, new id.
    Core copies the original's sales manager."""
    return await _post_slot("crm/revisit-visits/", visit_id, selected_date, selected_time)


async def _post_slot(path: str, visit_id: int, selected_date: str, selected_time: str) -> dict:
    body = {"visit_id": visit_id, "selected_date": selected_date, "selected_time": selected_time}
    async with _client() as client:
        try:
            r = await client.post(path, json=body)
        except httpx.HTTPError as e:
            log.warning("%s visit=%s NETWORK %s", path, visit_id, e)
            return {"status": "error", "detail": "Couldn't reach the booking service"}
    log.info("%s visit=%s date=%s slot=%s -> %s", path, visit_id, selected_date, selected_time, r.status_code)
    if r.status_code == 404 and "html" in r.headers.get("content-type", "").lower():
        # a route-level 404 (HTML), not "visit not found" (JSON) — this Core build
        # predates the endpoint. Prod answered exactly this before the release landed.
        return {"status": "error", "detail": "This isn't available on Openhouse Core yet."}
    if r.status_code >= 400:
        return {"status": "error", "detail": _err_text(r)}
    return {"status": "ok", "visit": r.json()}


async def reassign_visit(visit_id: int, smid: int) -> dict:
    """Move a visit to another accompanying RM: PATCH schedule-visits/{id}/ with ONLY
    `sales_manager`. {status, sales_manager?|detail}.

    A true partial update — probed on staging and prod (24 Sep): it changes
    salesManager/salesManagerId/updatedAt and nothing else, so unlike the PUT above there
    is no slot to echo back. Core sends the NEW RM an in-app + push "Lead Assignment";
    the previous RM is not told, and WhatsApp is not used.
    ⚠️ In this response `salesManager` is the RM's ID; in GET crm/visits/ it is their
    NAME (the id there is `salesManagerId`, a string)."""
    async with _client() as client:
        try:
            r = await client.patch(f"schedule-visits/{visit_id}/", json={"sales_manager": smid})
        except httpx.HTTPError as e:
            log.warning("reassign visit=%s NETWORK %s", visit_id, e)
            return {"status": "error", "detail": "Couldn't reach the booking service"}
    log.info("reassign visit=%s sm=%s -> %s", visit_id, smid, r.status_code)
    if r.status_code == 400 and "salesManager" in (r.json() if "json" in r.headers.get("content-type", "") else {}):
        # {"salesManager": ["Invalid pk \"…\" - object does not exist."]} — Core has no
        # active SalesManager with that id
        return {"status": "error", "detail": "Openhouse doesn't recognise that RM's SMID (unknown or inactive)."}
    if r.status_code >= 400:
        return {"status": "error", "detail": _err_text(r)}
    return {"status": "ok", "sales_manager": r.json().get("salesManager")}


async def fetch_brochure(home_id: int) -> dict:
    """A home's brochure PDF — GET homes/{id}/brochure/. {status, url?, filename?|detail}.

    Core renders it once and caches it on GCS; repeat calls return the same URL in
    ~0.2s. The CRM variant carries no broker contact. ⚠️ The keys are camelCase
    (`brochureUrl`) — the doc they sent says `brochure_url`, which does not exist.
    The first render can take a while, hence the longer timeout."""
    async with _client() as client:
        try:
            r = await client.get(f"homes/{home_id}/brochure/", timeout=90.0)
        except httpx.HTTPError as e:
            log.warning("brochure home=%s NETWORK %s", home_id, e)
            return {"status": "error", "detail": "Couldn't reach Openhouse Core"}
    log.info("brochure home=%s -> %s", home_id, r.status_code)
    if r.status_code == 404:
        return {"status": "not_found", "detail": f"Openhouse has no home {home_id}"}
    if r.status_code >= 400:
        return {"status": "error", "detail": _err_text(r)}
    b = r.json()
    return {"status": "ok", "url": b["brochureUrl"], "filename": b["filename"]}
