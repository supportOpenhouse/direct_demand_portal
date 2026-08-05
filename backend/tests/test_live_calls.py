"""Live Calls — the RM-facing view of a running campaign.

The queries need a live Postgres, so as in test_wa_assign.py these assert the *rules*
the SQL encodes: the parts that would silently show one RM another RM's calls, or
roll the day over mid-shift, if someone edited them.
"""
import re

import pytest

from app.routers import live_calls


def _sql(stmt) -> str:
    return re.sub(r"\s+", " ", str(stmt)).strip()


class _Result:
    """Just enough of a SQLAlchemy Result for `.mappings().first()`."""

    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _FakeConn:
    def __init__(self, calls, row):
        self.calls, self._row = calls, row

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return _Result(self._row)


class _FakeEngine:
    """Records what a transition would run, without a database."""

    def __init__(self, row=None):
        self.calls, self._row = [], row

    def begin(self):
        calls, row = self.calls, self._row

        class _Ctx:
            async def __aenter__(self_):
                return _FakeConn(calls, row)

            async def __aexit__(self_, *exc):
                return False

        return _Ctx()


@pytest.fixture
def published(monkeypatch):
    """Capture what each transition publishes instead of touching Redis."""
    sent = []

    async def _fake_publish(channel, payload):
        sent.append((channel, payload))

    monkeypatch.setattr("app.events.publish", _fake_publish)
    monkeypatch.setattr("app.routers.bonvoice.publish", _fake_publish, raising=False)
    monkeypatch.setattr("app.services.dialer.publish", _fake_publish, raising=False)
    return sent


async def test_the_hangup_publishes_to_the_rm_whose_slot_it_freed(published):
    """The hangup is what flips dialing → done. If it doesn't announce that, the RM's
    page keeps showing 'Ringing…' for a call that already ended, and the row never
    reaches the Completed list to be marked."""
    from app.routers.bonvoice import _release_dial_slot

    engine = _FakeEngine(row={"id": "q1", "rm_email": "Asha@X.com"})
    await _release_dial_slot(engine, {"callType": "2", "eventID": "ev1", "Status": "ANSWER"})

    assert published == [
        (live_calls_channel("asha@x.com"), {"type": "call_ended", "queue_item_id": "q1"})]


async def test_an_answer_event_does_not_announce_the_call_as_ended(published):
    """callType 1 means the lead picked up; the call is still live. Announcing an end
    here would move the row to Completed mid-conversation."""
    from app.routers.bonvoice import _release_dial_slot

    engine = _FakeEngine(row={"id": "q1", "rm_email": "asha@x.com"})
    await _release_dial_slot(engine, {"callType": "1", "eventID": "ev1"})

    assert published == []


async def test_a_hangup_for_an_already_closed_slot_publishes_nothing(published):
    """Both legs report a hangup, and the WHERE on status='dialing' makes the second a
    no-op. Publishing on it would nudge the page for a call it already handled."""
    from app.routers.bonvoice import _release_dial_slot

    engine = _FakeEngine(row=None)  # UPDATE matched nothing
    await _release_dial_slot(engine, {"callType": "2", "eventID": "ev1"})

    assert published == []


def test_the_hangup_returns_the_rm_it_freed():
    """The event is addressed per RM, so the UPDATE has to hand back whose slot it
    was — there is no second query to look it up."""
    from app.routers import bonvoice

    src = _sql(bonvoice._RELEASE_SLOT)
    assert "RETURNING" in src
    assert "rm_email" in src.split("RETURNING", 1)[1]


def test_the_poller_returns_the_rm_it_freed():
    """The poller closes calls the webhook never reported. It must announce them too,
    or a dropped callback leaves the page stuck on a call that ended minutes ago."""
    from app.services import dialer

    src = _sql(dialer._POLL_CLOSE)
    assert "RETURNING" in src
    assert "rm_email" in src.split("RETURNING", 1)[1]


def live_calls_channel(email: str) -> str:
    from app.events import rm_channel

    return rm_channel(email)


# --- marking the result from Live Calls ------------------------------------------


def test_the_two_hour_cooldown_is_waivable_by_parameter():
    """The 2h block exists to stop an RM hammering "No" without dialling. A campaign
    call was placed by the scheduler, not chosen by the RM, so the rationale doesn't
    apply — and a campaign with cooldown_minutes < 120 legitimately redials inside
    that window. Left unwaivable, the RM's second result is silently discarded."""
    from app.routers import leads

    src = _sql(leads._CALL_RESULT_NO)
    assert ":skip_cooldown" in src
    blocked = src.split("AS blocked", 1)[0]
    assert "NOT CAST(:skip_cooldown AS boolean)" in blocked


def test_the_cooldown_still_applies_when_it_is_not_waived():
    """The manual worklist must keep its spam guard — the waiver is opt-in per call,
    not a removal."""
    from app.routers import leads

    src = _sql(leads._CALL_RESULT_NO)
    assert "last_no_timestamp > now() - interval '2 hours'" in src


def test_queue_ownership_is_checked_against_the_caller_and_the_lead():
    """The client sends a queue_item_id; whether that row is theirs is never the
    client's call. Matching the lead too stops a valid id of one's own being used to
    stamp a result onto a different lead's row."""
    from app.routers import leads

    src = _sql(leads._MY_QUEUE_ITEM)
    assert "lower(rm_email) = lower(:email)" in src
    assert "lead_id = :lead" in src


def test_marking_records_who_marked_it_and_when():
    """Otherwise a campaign report can't tell an unmarked call from one marked by
    somebody else."""
    from app.routers import leads

    src = _sql(leads._STAMP_CALL_RESULT)
    assert "call_result = :result" in src
    assert "call_result_at = now()" in src
    assert "call_result_by = :email" in src


def test_every_lead_column_selected_actually_exists():
    """These queries only ever run against a real Postgres, so a column that doesn't
    exist is a 500 on the page and nowhere else — it can't be caught by reading the
    SQL. `leads` has budget_band, not budget; that shipped and broke Live Calls
    outright. Checking the selected names against the model closes the gap."""
    from app.models import Lead

    real = set(Lead.__table__.columns.keys())
    selected = set()
    for stmt in (live_calls._NOW_CALLING, live_calls._COMPLETED_TODAY,
                 live_calls.upcoming_sql("assigned"), live_calls.upcoming_sql("round_robin")):
        # `l` is the leads alias in every one of these queries
        selected |= set(re.findall(r"\bl\.(\w+)", str(stmt)))

    assert selected <= real, f"not columns on leads: {sorted(selected - real)}"


def test_now_calling_is_scoped_to_the_caller():
    """The whole point of the page is "who am *I* on with". An unscoped query would
    show whichever RM the scheduler happened to dial most recently."""
    src = _sql(live_calls._NOW_CALLING)
    assert "lower(q.rm_email) = lower(:email)" in src
    assert "q.status = 'dialing'" in src


def test_completed_is_scoped_to_the_caller():
    src = _sql(live_calls._COMPLETED_TODAY)
    assert "lower(q.rm_email) = lower(:email)" in src


def test_completed_uses_the_ist_day_not_utc():
    """Calling windows are IST wall-clock (10:00–19:00), so the RM's "today" is the
    IST day. On UTC the Completed list would clear itself at 05:30 IST — mid-shift
    for an early campaign — and take unmarked calls out of reach with it."""
    src = _sql(live_calls._COMPLETED_TODAY)
    assert src.count("Asia/Kolkata") == 2, "both sides of the day compare must be IST"


def test_completed_surfaces_whether_the_rm_marked_it():
    """NULL call_result is what renders the 'needs result' badge — without it
    selected, every row would look already handled."""
    assert "q.call_result" in _sql(live_calls._COMPLETED_TODAY)


def test_upcoming_is_owner_scoped_only_under_assigned():
    """rm_email is pre-stamped only by assign_owners, under the 'assigned' strategy.
    Under round_robin it stays NULL until _dial_next claims the row, so filtering on
    it there would always return an empty queue."""
    assert "rm_email" in _sql(live_calls.upcoming_sql("assigned"))
    assert "rm_email" not in _sql(live_calls.upcoming_sql("round_robin"))
    assert "rm_email" not in _sql(live_calls.upcoming_sql("least_load"))


def test_upcoming_follows_the_scheduler_claim_order():
    """_dial_next claims ORDER BY position, id. Showing any other order would tell
    the RM the wrong lead is next."""
    for strategy in ("assigned", "round_robin"):
        order = _sql(live_calls.upcoming_sql(strategy)).split("ORDER BY", 1)[1].strip()
        assert order.startswith("q.position, q.id")


def test_upcoming_only_lists_leads_still_waiting():
    assert "q.status = 'pending'" in _sql(live_calls.upcoming_sql("round_robin"))


def test_live_campaign_picks_the_one_whose_window_is_open():
    """_assert_no_rm_conflict only rejects campaigns whose windows OVERLAP, so an RM
    can sit in two running campaigns at different hours. Only the in-window one is
    dialling them right now."""
    morning = {"id": "m", "window_start": "10:00", "window_end": "13:00"}
    evening = {"id": "e", "window_start": "16:00", "window_end": "19:00"}

    picked = live_calls.live_campaign(
        [morning, evening], in_window=lambda s, e: (s, e) == ("16:00", "19:00"))

    assert picked is evening


def test_live_campaign_is_none_outside_every_window():
    """Before 10:00 nobody is being dialled — the page must say idle, not pick a
    campaign that is merely 'running'."""
    rows = [{"id": "m", "window_start": "10:00", "window_end": "13:00"}]
    assert live_calls.live_campaign(rows, in_window=lambda s, e: False) is None


async def test_the_no_database_answer_has_the_same_shape_as_a_real_one(monkeypatch):
    """The endpoint returns early when DATABASE_URL is unset. If that early answer
    omits a key the real one has, the page reads `undefined` for it — and
    upcoming_is_shared reading undefined means a shared pool silently renders as if
    those leads were the RM's own."""
    monkeypatch.setattr("app.routers.live_calls.neon_engine", lambda: None)

    body = await live_calls.my_calls(user={"email": "rm@x.com"})

    assert set(body) == {"campaign", "upcoming_is_shared", "now_calling",
                         "upcoming", "completed"}


def test_sse_frame_is_data_prefixed_and_double_newline_terminated():
    """SSE splits on a blank line. Without the second \\n the browser buffers the
    event forever and the page looks frozen while calls come and go."""
    assert live_calls.sse_frame({"type": "call_ended"}) == 'data: {"type": "call_ended"}\n\n'


def test_sse_frame_never_emits_a_raw_newline_inside_the_payload():
    """A lead name or a dial failure detail can contain a newline. Unescaped, it ends
    the frame early and the client parses half an event as a whole one."""
    frame = live_calls.sse_frame({"detail": "line one\nline two"})

    assert frame.endswith("\n\n")
    assert frame.count("\n") == 2


def test_sse_keepalive_is_a_comment_not_an_event():
    """Render closes idle connections, so the stream must emit something during quiet
    stretches — but a comment, or the client would parse periodic empty events."""
    assert live_calls.SSE_KEEPALIVE.startswith(":")
    assert live_calls.SSE_KEEPALIVE.endswith("\n\n")
    assert "data:" not in live_calls.SSE_KEEPALIVE
