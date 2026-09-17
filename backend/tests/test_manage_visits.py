"""Manage visits: the slot-string contract, the two completion paths, and the rule that
decides what counts as a revisit. No DB and no network — these assert the rules the code
encodes, per tests/test_wa_assign.py."""
import ast
import inspect
import re
from pathlib import Path

from app.routers import visits as visits_router
from app.services.crm_booking import LEAD_STATUS_VALUES, SLOT_VALUES, SM_FEEDBACK_FIELDS

FRONTEND = Path(__file__).parents[2] / "frontend" / "src"


def test_slots_are_the_spaced_form_core_uses():
    """Core stores selected_time as free text and compares slots as STRINGS, so
    "3-5 PM" and "3 - 5 PM" are two different slots to it — the unspaced form silently
    defeats its duplicate-visit check. The API guide and the Openhouse app both space it."""
    assert SLOT_VALUES == ["9 - 11 AM", "11 - 1 PM", "1 - 3 PM", "3 - 5 PM", "5 - 7 PM", "7 - 9 PM"]
    assert all(" - " in s for s in SLOT_VALUES), "a slot without spaces is a different slot to Core"


def test_the_frontend_sends_exactly_the_slots_the_backend_accepts():
    """lib/slots.ts is a hand-kept mirror of SLOT_VALUES and the booking endpoints reject
    anything not in the list — so a drift here is a 400 on every booking, from the only
    UI that books."""
    ts = (FRONTEND / "lib" / "slots.ts").read_text()
    block = ts.split("export const SLOTS", 1)[1].split("];", 1)[0]
    labels = re.findall(r'label:\s*"([^"]+)"', block)
    assert labels == SLOT_VALUES, f"slots.ts and crm_booking.py disagree: {labels} vs {SLOT_VALUES}"


def test_completion_omits_the_assisted_keys_when_they_are_not_given():
    """Core picks the OTP vs assisted path from WHICH KEYS are present, so sending
    lead_status=None / sm_demand_feedback={} would claim a feedback form was filled in
    when it wasn't."""
    src = inspect.getsource(__import__("app.services.crm_booking", fromlist=["x"]).complete_visit)
    assert 'if lead_status:' in src, "lead_status must be added conditionally, not always"
    assert re.search(r"if clean:", src), "sm_demand_feedback must be omitted when every answer is blank"
    # and blank answers are dropped rather than sent as ""
    assert "if k in SM_FEEDBACK_FIELDS and v" in src


def test_complete_and_cancel_echo_the_visits_own_slot():
    """⚠️ PUT /schedule-visits/{id}/ WRITES selected_date/selected_time — it does not
    check them. Cancelling with a wrong date MOVES the visit (verified on staging: 7595
    landed on 1999-01-01). So the payload must come from a fresh read of the visit, never
    from the caller."""
    src = inspect.getsource(__import__("app.services.crm_booking", fromlist=["x"])._put_status)
    assert "_fetch_visit(client, visit_id)" in src, "must read the visit before writing it"
    assert 'v.get("selectedDate")' in src and 'v.get("selectedTime")' in src
    sig = inspect.signature(__import__("app.services.crm_booking", fromlist=["x"])._put_status)
    assert "selected_date" not in sig.parameters, "the caller must not be able to supply the slot"


def test_a_revisit_is_the_same_property_not_just_another_visit():
    """The definition that drives the stage: a buyer touring three different societies has
    three first visits and stays visit_scheduled; going back to one they have already seen
    is what makes it revisit_scheduled."""
    src = inspect.getsource(visits_router.book)
    assert "seen_homes" in src, "the revisit test must be against homes already visited"
    assert 'r["home_id"] in seen_homes' in src
    # the old rule — any second booking on the lead — must be gone
    assert "WHEN stage = 'visit_scheduled' THEN 'revisit_scheduled'" not in src, \
        "that is the OLD rule: it made every second visit a revisit, whatever the property"


def test_stage_moves_stay_forward_only():
    """Terminal leads keep their stage, and a lead already in the pipeline is never
    demoted back to visit_scheduled by a booking for a new property."""
    for fn in (visits_router.book, visits_router.revisit):
        src = inspect.getsource(fn)
        assert "WHEN stage IN ('converted','future_prospect','rejected','rnr') THEN stage" in src
    assert "WHEN stage = 'revisit_scheduled' THEN stage" in inspect.getsource(visits_router.book)


def test_cancelling_a_visit_does_not_touch_the_lead_stage():
    """A cancelled visit doesn't un-happen the ones before it, and stage writes are
    forward-only everywhere else — rolling one back here would be the one exception."""
    src = inspect.getsource(visits_router.cancel)
    assert "UPDATE leads" not in src


def test_every_manage_action_records_what_it_did():
    """Reports derive entirely from activity_log, so an action with no event is invisible
    there — which is exactly how bulk WhatsApp lead creation went unnoticed."""
    actions = {
        visits_router.cancel: "visit_cancelled",
        visits_router.complete: "visit_completed",
        visits_router.reschedule: "visit_rescheduled",
        visits_router.revisit: "visit_booked",
    }
    for fn, action in actions.items():
        assert f'action="{action}"' in inspect.getsource(fn), f"{fn.__name__} logs nothing"


def test_the_feedback_form_matches_core_field_for_field():
    """The six sm_demand_feedback keys and the lead_status values are Core's, not ours —
    a key it doesn't know is dropped silently, so the answer would just vanish."""
    assert SM_FEEDBACK_FIELDS == [
        "time_spent_on_site", "society_amenity_tour", "price_discussion",
        "client_queries", "closing_signal", "buyer_primary_concern",
    ]
    assert LEAD_STATUS_VALUES == ["hot", "warm", "cold", "future_prospect", "dead", "select_status"]

    ts = (FRONTEND / "lib" / "api.ts").read_text()
    block = ts.split("SM_FEEDBACK_QUESTIONS", 1)[1].split("];", 1)[0]
    assert re.findall(r'key:\s*"([^"]+)"', block) == SM_FEEDBACK_FIELDS, "the form asks different questions"
    statuses = ts.split("VISIT_LEAD_STATUS = [", 1)[1].split("]", 1)[0]
    assert re.findall(r'"([^"]+)"', statuses) == LEAD_STATUS_VALUES


def test_a_dead_core_route_reads_as_not_available_yet():
    """Prod answered an HTML 404 for reschedule-visits/ before Core deployed the release,
    while a JSON 404 means the VISIT wasn't found. Same status code, opposite meanings —
    telling an RM "visit not found" when the endpoint simply isn't live is a bug hunt."""
    src = inspect.getsource(__import__("app.services.crm_booking", fromlist=["x"])._post_slot)
    assert 'r.status_code == 404 and "html" in' in src
    assert "isn't available on Openhouse Core yet" in src


def test_the_manage_endpoints_are_mounted():
    routes = {r.path for r in visits_router.router.routes}
    for p in ("/visits/{visit_id}/cancel", "/visits/{visit_id}/complete",
              "/visits/{visit_id}/reschedule", "/visits/{visit_id}/revisit"):
        assert p in routes, f"{p} is not registered"


def test_no_module_parses_the_frontend_slot_list_at_runtime():
    """These mirrors are checked HERE, in a test. Reading slots.ts from the app at runtime
    would make the API depend on the frontend source tree being deployed beside it."""
    for py in (Path(__file__).parents[1] / "app").rglob("*.py"):
        tree = ast.parse(py.read_text())
        assert "slots.ts" not in ast.dump(tree), f"{py.name} reads the frontend source"


def test_a_cancelled_visit_does_not_make_the_next_one_a_revisit():
    """A cancelled visit never happened, so re-booking that property is the buyer's FIRST
    visit to it. Counting it as a revisit would push the lead into Pipeline Leads off a
    visit nobody attended."""
    src = inspect.getsource(visits_router.book)
    assert "status <> 'cancelled'" in src, "seen_homes must exclude cancelled visits"


def test_rebooking_a_cancelled_property_uses_the_normal_booking_path():
    """Not Core's revisit endpoint — that one requires a COMPLETED source visit and
    answers 400 'Revisit is only allowed when the prior visit is completed.' for a
    cancelled one (verified on staging)."""
    modal = (FRONTEND / "features" / "ManageVisitsModal.tsx").read_text()
    rebook = modal.split('if (kind === "rebook")', 1)[1].split("return;", 1)[0]
    assert "rebook.mutate" in rebook
    for field in ("home_id", "buyer_name", "buyer_mobile", "rm_accompanying", "lead_id"):
        assert field in rebook, f"the booking payload is missing {field}"
    assert "useRevisitVisit" not in rebook


def test_the_rebook_button_is_hidden_when_the_row_cannot_be_booked():
    """5 of 97 cancelled visits are old sheet-synced rows with no buyer stored. Offering a
    button that can only fail validation is worse than saying why it isn't there."""
    modal = (FRONTEND / "features" / "ManageVisitsModal.tsx").read_text()
    guard = modal.split("const canRebook", 1)[1].split(";", 1)[0]
    assert "home_id" in guard and "buyer_name" in guard and "buyer_mobile" in guard


def test_a_per_unit_booking_failure_is_not_reported_as_success():
    """POST /visits/book answers 200 with a per-unit results[] — a refusal arrives INSIDE
    a success, so reporting off the HTTP status alone would claim a booking that isn't."""
    modal = (FRONTEND / "features" / "ManageVisitsModal.tsx").read_text()
    assert "results?.[0]" in modal and "if (r && !r.ok)" in modal


def test_visit_details_are_built_from_the_model_minus_the_hidden_fields():
    """Not a hand-written SELECT. A column added to app_visit_data shows up in the card
    on its own, and the five hidden fields are excluded BY CONSTRUCTION — a list you have
    to remember to keep five names out of is a list that eventually leaks them."""
    from app.services.app_visit_data import HIDDEN_FIELDS
    from app.routers.visits import _detail_columns

    cols = set(_detail_columns())
    assert not (cols & set(HIDDEN_FIELDS)), f"leaking {cols & set(HIDDEN_FIELDS)}"
    # the plumbing columns are ours, not the visit's story
    assert not (cols & {"visit_id", "found", "data", "crm_updated_at", "fetched_at"})
    assert {"status", "society_name", "sales_manager", "sm_closing_signal"} <= cols


def test_the_details_endpoint_keeps_core_and_our_booking_apart():
    """`core` is null until that visit has been pulled from Openhouse — the fill is a
    manual script with no cron, so a visit booked a minute ago has none. `booking` is ours
    and always there, and is the ONLY place the booker and accompanying RM exist."""
    src = inspect.getsource(visits_router.visit_details)
    assert '"core": dict(core) if core else None' in src, "a missing Core row must read as null, not {}"
    assert "FROM crm_visits WHERE visit_id" in src
    assert "booked_by" in src and "rm_accompanying" in src


def test_the_expanded_card_never_hardcodes_the_hidden_fields_back_in():
    """The exclusion is server-side, so the browser never receives them. This catches
    someone adding a label or a group entry for one, which would be a strong hint they
    meant to serve it too."""
    for f in ("api.ts", ):
        ts = (FRONTEND / "lib" / f).read_text()
        block = ts.split("VISIT_DETAIL_GROUPS", 1)[1].split("VISIT_LEAD_STATUS", 1)[0]
        for hidden in ("profession", "broker_name", "broker_contact", "broker_alt_contact", "company_name"):
            assert hidden not in block, f"{hidden} listed in the visit detail UI"


def test_an_unlabelled_core_column_still_renders():
    """Core adds fields. A value under a rough label beats it silently not appearing —
    which is what a strict label lookup would do."""
    modal = (FRONTEND / "features" / "ManageVisitsModal.tsx").read_text()
    assert "VISIT_DETAIL_LABELS[k] ?? prettify(k)" in modal
    assert 'title: "Other"' in modal, "unlisted keys need a group to land in"


def test_a_slot_is_accepted_in_any_spelling_and_stored_one_way():
    """"3-5 PM" and "3 - 5 PM" are one slot to a person and two to Core, which compares
    them as strings. Rejecting a spelling we understand perfectly well just breaks booking
    for whoever is behind — a deployed frontend lags a backend deploy, and 297 prod visits
    were booked unspaced by our own older builds."""
    from app.services.crm_booking import canonical_slot

    for spelling in ("3 - 5 PM", "3-5 PM", "3 -5 pm", "  3-5 PM ", "3-5", "3 - 5"):
        assert canonical_slot(spelling) == "3 - 5 PM", spelling
    # every canonical value is its own canonical form — no slot rewrites to a different one
    for v in SLOT_VALUES:
        assert canonical_slot(v) == v


def test_an_unknown_slot_is_still_rejected():
    """Normalising must not turn into accepting anything. Core stores selected_time as
    free text, so a slot it doesn't know is stored verbatim and silently defeats its own
    duplicate-visit check."""
    from app.services.crm_booking import canonical_slot

    for junk in ("banana o'clock", "4-6 PM", "", None, "3", "3 - 5 QM"):
        assert canonical_slot(junk) is None, junk


def test_every_entry_point_normalises_before_it_writes_anything():
    """Three endpoints take a slot. Each must canonicalise BEFORE the Core call, our
    crm_visits copy and the activity row — a slot normalised in one of the three is the
    bug this replaced, just moved."""
    for fn in (visits_router.book, visits_router.reschedule, visits_router.revisit):
        src = inspect.getsource(fn)
        assert "canonical_slot(req.selected_time)" in src, f"{fn.__name__} doesn't normalise"
        assert 'req.model_copy(update={"selected_time": slot})' in src, \
            f"{fn.__name__} normalises but keeps using the raw value"
        assert "if req.selected_time not in SLOT_VALUES" not in src, f"{fn.__name__} still rejects a spelling"
