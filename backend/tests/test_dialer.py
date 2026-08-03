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


class _FakeConn:
    def __init__(self, calls):
        self.calls = calls

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))


class _FakeEngine:
    """Records what the release would run, without a database."""

    def __init__(self):
        self.calls = []

    def begin(self):
        calls = self.calls

        class _Ctx:
            async def __aenter__(self_):
                return _FakeConn(calls)

            async def __aexit__(self_, *exc):
                return False

        return _Ctx()


async def _release(body):
    from app.routers.bonvoice import _release_dial_slot
    engine = _FakeEngine()
    await _release_dial_slot(engine, body)
    return engine.calls


async def test_hangup_frees_the_slot_even_with_no_call_id():
    """The regression: a stuck 'dialing' row shows "Ringing…" forever AND costs that RM
    the rest of the campaign, so releasing must not depend on the log row's callID."""
    calls = await _release({"callType": "2", "eventID": "ev123", "Status": "ANSWER"})
    assert len(calls) == 1
    assert calls[0][1] == {"eid": "ev123", "outcome": "ANSWER"}
    assert "dial_queue" in calls[0][0]


async def test_only_hangup_releases_the_slot():
    assert await _release({"callType": "0", "eventID": "ev123"}) == []  # initiated
    assert await _release({"callType": "1", "eventID": "ev123"}) == []  # answered
    assert await _release({"callType": "2"}) == []                      # nothing to match on


def test_calling_window():
    assert _in_window("00:00", "23:59") is True
    assert _in_window("", "") is True          # unset window never blocks dialling
    assert _in_window("garbage", "19:00") is True
