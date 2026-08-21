"""The rule compiler is a trust boundary — the tree comes straight from the browser.
Nothing it contains may reach SQL except as a bound parameter."""
import pytest

from app.services.dialer import BASE_PREDICATE, _in_window, aliases_for, compile_rules


def cond(field, op, value):
    return {"type": "condition", "field": field, "op": op, "value": value}


def group(combinator, *children):
    return {"type": "group", "combinator": combinator, "children": list(children)}


def test_values_are_bound_never_inlined():
    sql, params = compile_rules(group("AND", cond("society", "IN", ["Gaur City'; DROP TABLE leads--"])))
    assert "DROP TABLE" not in sql
    assert list(params.values()) == ["Gaur City'; DROP TABLE leads--"]


def test_unknown_field_and_operator_are_rejected():
    with pytest.raises(ValueError):
        compile_rules(group("AND", cond("password", "IN", ["x"])))
    with pytest.raises(ValueError):
        compile_rules(group("AND", cond("society", "LIKE", ["x"])))  # not on the multi whitelist
    with pytest.raises(ValueError):
        compile_rules({"type": "group", "combinator": "OR; DELETE FROM leads", "children": []})


def test_empty_selection_means_no_filter():
    """Matches the builder's live preview: an untouched condition matches everything."""
    assert compile_rules(cond("society", "IN", []))[0] == "TRUE"
    assert compile_rules(cond("created_at", "BETWEEN", ["", ""]))[0] == "TRUE"
    assert compile_rules(group("AND"))[0] == "TRUE"


def test_and_or_nesting_keeps_its_shape():
    sql, params = compile_rules(group(
        "AND",
        cond("miss_count", "<=", 2),
        group("OR", cond("stage", "IN", ["new"]), cond("source", "IN", ["meta"])),
    ))
    assert " AND " in sql and " OR " in sql
    assert sql.count("(") == sql.count(")")
    assert set(params.values()) == {2.0, "new", "meta"}


def test_not_in_still_matches_rows_with_no_value():
    sql, _ = compile_rules(cond("stage", "NOT IN", ["converted"]))
    assert "IS NULL" in sql  # a lead with no stage isn't 'converted'


def test_number_condition_needs_a_number():
    with pytest.raises(ValueError):
        compile_rules(cond("miss_count", "<=", "; DROP TABLE leads"))


def test_depth_is_capped():
    node = cond("miss_count", "=", 1)
    for _ in range(8):
        node = group("AND", node)
    with pytest.raises(ValueError):
        compile_rules(node)


def test_base_predicate_excludes_undialable_leads():
    assert "phone IS NOT NULL" in BASE_PREDICATE and "is_test = false" in BASE_PREDICATE


def test_assigned_strategy_matches_every_way_a_name_is_written():
    """`leads.assigned_to` is free text: the sheet writes 'Saumya', the Assign button
    writes 'Saumya Behera'. Both must route to the same RM."""
    a = aliases_for("Saumya Behera", "Saumya B")
    assert "saumya behera" in a and "saumya" in a and "saumya b" in a
    assert all(x == x.lower() for x in a)
    assert aliases_for(None, None) == []          # no name = matches nothing, not everything
    assert aliases_for("  ", "") == []


def test_calling_windows_overlap_is_half_open():
    """Two running campaigns may not share an RM at overlapping hours — the scheduler
    counts live calls per campaign, so both would ring the same handset at once."""
    from app.services.dialer import windows_overlap

    assert windows_overlap("10:00", "19:00", "11:00", "12:00")   # fully contained
    assert windows_overlap("10:00", "12:00", "11:00", "14:00")   # partial
    assert windows_overlap("10:00", "19:00", "10:00", "19:00")   # identical
    assert not windows_overlap("10:00", "13:00", "13:00", "18:00")  # touching ≠ overlapping
    assert not windows_overlap("10:00", "12:00", "14:00", "16:00")  # disjoint
    # a malformed window means "always on" (matching _in_window), so it conflicts
    # with everything rather than silently letting a double-dial through
    assert windows_overlap("", "", "14:00", "16:00")
    assert windows_overlap("garbage", "nonsense", "00:00", "00:01")


def test_unowned_skips_are_tagged_with_the_shared_constant():
    """'targeted leads' counts queue rows minus the ones skipped as not-in-pool, and
    it tells them apart from Stop-skipped rows by this exact `detail` string. If the
    literal here and the one in the stats filter drift, a campaign aimed at one RM's
    4 leads silently reports every rule match again (1727)."""
    import asyncio

    from app.services.dialer import UNOWNED_DETAIL, assign_owners

    calls = []

    class _Res:
        rowcount = 3

    class _Conn:
        async def execute(self, stmt, params=None):
            calls.append((str(stmt), params or {}))
            return _Res()

    skipped = asyncio.run(assign_owners(_Conn(), "cid", [("rm@x.in", ["rm"])]))
    assert skipped == 3
    skip_stmt, skip_params = calls[-1]
    assert "status = 'skipped'" in skip_stmt
    assert skip_params["unowned"] == UNOWNED_DETAIL
    assert UNOWNED_DETAIL not in skip_stmt  # bound, not inlined


class _Result:
    """Just enough of a SQLAlchemy Result for `.mappings().first()`. The release
    statement RETURNs the freed row so Live Calls can be notified; returning None here
    would send _release_dial_slot down its except branch and these tests would pass
    without ever exercising the real path."""

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
    """Records what the release would run, without a database."""

    def __init__(self, row=None):
        self.calls = []
        self._row = row

    def begin(self):
        calls, row = self.calls, self._row

        class _Ctx:
            async def __aenter__(self_):
                return _FakeConn(calls, row)

            async def __aexit__(self_, *exc):
                return False

        return _Ctx()


async def _release(body, row={"id": "q1", "rm_email": "rm@x.com", "lead_id": "L1"}):
    from app.routers.bonvoice import _release_dial_slot
    engine = _FakeEngine(row=row)
    await _release_dial_slot(engine, body)
    return engine.calls


async def test_hangup_frees_the_slot_even_with_no_call_id():
    """The regression: a stuck 'dialing' row shows "Ringing…" forever AND costs that RM
    the rest of the campaign, so releasing must not depend on the log row's callID."""
    calls = await _release({"callType": "2", "eventID": "ev123", "Status": "ANSWER"})
    # The release, plus the activity row that now rides in the same transaction — the
    # count isn't the point, the release running with the right params is.
    assert "dial_queue" in calls[0][0]
    assert calls[0][1] == {"eid": "ev123", "outcome": "ANSWER", "answered": True, "ends": True}
    assert any("activity_log" in c[0] for c in calls), "the dial should be recorded too"


async def test_answer_is_recorded_without_ending_the_call():
    """The answer event decides whether a retry is owed, but the call is still up —
    ending it here would free the RM mid-conversation and dial the next lead."""
    calls = await _release({"callType": "1", "eventID": "ev123"})
    assert calls[0][1]["answered"] is True and calls[0][1]["ends"] is False
    # an answer is not an end, so no call_dialled row yet
    assert not any("activity_log" in c[0] for c in calls)


async def test_nothing_else_touches_the_slot():
    assert await _release({"callType": "0", "eventID": "ev123"}) == []  # initiated
    assert await _release({"callType": "2"}) == []                      # nothing to match on


"""The call-log poller parses a response shape the docs describe but don't pin down,
so it has to survive the plausible variations rather than assume one."""


def test_log_records_unwraps_whatever_envelope_is_used():
    from app.routers.bonvoice import log_records
    rec = {"callID": "c1", "Status": "ANSWER"}
    assert log_records([rec]) == [rec]
    assert log_records({"data": [rec]}) == [rec]
    assert log_records({"result": {"records": [rec]}}) == [rec]
    assert log_records(rec) == [rec]                    # a bare record
    assert log_records({"responseCode": 200}) == []      # an envelope with no records
    assert log_records("nope") == []


def test_call_state_reads_end_and_answer_however_they_are_spelled():
    from app.routers.bonvoice import read_call_state
    # hangup lifecycle marker
    assert read_call_state([{"callType": "2"}])[0] is True
    # or simply an end time, whatever the casing
    assert read_call_state([{"EndTime": "2026-08-03 12:41:00"}])[0] is True
    assert read_call_state([{"endtime": "2026-08-03 12:41:00"}])[0] is True

    ended, answered, status = read_call_state([
        {"callType": "1", "Status": "ANSWERED"}, {"callType": "2", "Status": "ANSWERED"},
    ])
    assert (ended, answered, status) == (True, True, "ANSWERED")


def test_a_call_still_in_progress_is_left_alone():
    """No end marker means the call is still up — closing it here would hang up on the
    RM mid-conversation as far as the queue is concerned."""
    from app.routers.bonvoice import read_call_state
    ended, answered, _ = read_call_state([{"callType": "0", "StartTime": "2026-08-03 12:40:43"}])
    assert ended is False and answered is False
    assert read_call_state([]) == (False, False, None)


def test_calling_window():
    assert _in_window("00:00", "23:59") is True
    assert _in_window("", "") is True          # unset window never blocks dialling
    assert _in_window("garbage", "19:00") is True


# --- calling window must not already be over -------------------------------------


def test_a_window_that_ended_earlier_today_is_rejected():
    """_in_window is start <= now <= end with no midnight wrap, so a campaign started
    at 18:40 with a 10:00–17:00 window sits at 'running' and dials nobody until
    tomorrow. The admin gets no signal at all — the campaign just looks stuck."""
    from datetime import time as _t

    from app.services.dialer import window_has_passed

    assert window_has_passed("10:00", "17:00", now=_t(18, 40)) is True


def test_a_window_still_open_or_yet_to_open_is_allowed():
    from datetime import time as _t

    from app.services.dialer import window_has_passed

    assert window_has_passed("10:00", "19:00", now=_t(18, 40)) is False  # still inside
    assert window_has_passed("16:00", "19:00", now=_t(9, 0)) is False    # opens later


def test_a_window_ending_exactly_now_is_not_yet_past():
    """_in_window's bound is inclusive (now <= end), so this minute still dials."""
    from datetime import time as _t

    from app.services.dialer import window_has_passed

    assert window_has_passed("10:00", "17:00", now=_t(17, 0)) is False


def test_a_malformed_window_is_not_treated_as_past():
    """_in_window reads a broken window as 'always on'. Rejecting it here instead
    would block campaign creation on a value the dialer is happy to run."""
    from datetime import time as _t

    from app.services.dialer import window_has_passed

    assert window_has_passed("", "", now=_t(18, 40)) is False
    assert window_has_passed("garbage", "nonsense", now=_t(18, 40)) is False
