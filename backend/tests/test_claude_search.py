"""Search box → Claude mode. No database, no network: Claude is stubbed, and the SQL / the
router are checked for the rules they must encode (tests/test_wa_assign.py pattern)."""
import inspect
import json

import pytest
from fastapi import HTTPException

from app.routers import claude_search as router
from app.services import claude_search as cs


def _book(n: int) -> list[str]:
    return [json.dumps({"id": f"uuid-{i}", "name": f"Lead {i}"}) for i in range(1, n + 1)]


class _U:
    input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 1, 1, 0, 1


def test_a_row_can_never_break_the_table():
    """Rows are "|"-separated, one per line — a pipe or newline inside a remark would split
    a lead across columns or rows, and Claude would read it as someone else's data."""
    rows, ids = cs.compact([json.dumps({
        "id": "u1", "name": "A|B", "remarks": ["line one\nline two", "x"],
        "ever_connected": False, "confirmed_on_call": {"purpose": "Investment"}})])
    assert ids == ["u1"]
    row = rows[0]
    assert "\n" not in row and row.startswith("1|A/B|")
    assert row.count("|") == len(cs.COLUMNS)          # exactly one cell per column
    assert "line one line two ;; x" in row and "|no|" in row and "purpose=Investment" in row
    assert cs.HEADER.count("|") == len(cs.COLUMNS)


def test_parts_cover_every_row_once_in_order_and_fit_the_budget():
    rows = [f"{i}|" + "x" * 997 for i in range(1, 3001)]    # ~3M chars → 4 parts
    parts = cs.chunks(rows)
    assert [r for p in parts for r in p] == rows
    assert len(parts) == -(-sum(len(r) + 1 for r in rows) // cs.CHUNK_CHARS)
    assert all(sum(len(r) + 1 for r in p) <= cs.CHUNK_CHARS for p in parts)
    assert cs.chunks(rows[:5]) == [rows[:5]]                # a small book is one request


async def test_parts_are_searched_in_parallel_and_their_matches_unioned(monkeypatch):
    """No merge call: matches are combined (de-duped, out-of-range numbers dropped) and the
    numbers map back to the uuids that were sent. Notes are combined without repeats."""
    monkeypatch.setattr(cs, "CHUNK_CHARS", 200)
    calls = []

    async def fake_call(_client, system, user):
        calls.append((system, user))
        i = len(calls)
        return {"lead_numbers": [7 - i, 999], "note": "" if i > 1 else "Read 'weekend' as Sat/Sun."}, _U()

    monkeypatch.setattr(cs, "_call", fake_call)
    monkeypatch.setattr(cs, "_client", lambda: None)
    out = await cs.search("weekend visits", _book(6))
    assert out["parts"] > 1 and len(calls) == out["parts"]
    assert "part 1 of" in calls[0][0][1]["text"]
    assert out["lead_ids"] == [f"uuid-{7 - i}" for i in range(1, out["parts"] + 1)]
    assert out["note"] == "Read 'weekend' as Sat/Sun."


async def test_todays_date_rides_in_the_query_not_the_cached_prompt(monkeypatch):
    calls = []

    async def fake_call(_client, system, user):
        calls.append((system, user))
        return {"lead_numbers": [2], "note": ""}, _U()

    monkeypatch.setattr(cs, "_call", fake_call)
    monkeypatch.setattr(cs, "_client", lambda: None)
    out = await cs.search("who?", _book(3))
    system, user = calls[0]
    assert "Today is" in user and user.endswith("Search: who?")
    assert all("Today is" not in block["text"] for block in system)
    assert out == {**out, "lead_ids": ["uuid-2"], "note": "", "parts": 1}


def test_the_book_is_scoped_like_the_list_it_filters():
    """Role scope AND the page's segment — Claude reads exactly what that page could show."""
    assert "{scope}" in cs.BOOK_SQL and "NOT leads.is_test" in cs.BOOK_SQL
    src = inspect.getsource(router.claude_search)
    assert "_role_scope(user)" in src and "SEGMENTS[payload.segment]" in src


async def test_open_to_every_signed_in_user_and_unknown_segments_refused(monkeypatch):
    """Not admin-only since 13 Oct — safe because the book is role-scoped (an RM reads only
    their own leads), which test_the_book_is_scoped_like_the_list_it_filters pins."""
    from app.core.auth import current_user
    sig = inspect.signature(router.claude_search)
    assert sig.parameters["user"].default.dependency is current_user
    monkeypatch.setattr(router.get_settings(), "CLAUDE_API_KEY", "k")
    with pytest.raises(HTTPException) as e:
        await router.claude_search(router.SearchIn(query="hot leads", segment="nope"), {"role": "admin"})
    assert e.value.status_code == 400


def test_every_search_is_logged_even_when_it_fails():
    """The activity row is written in `finally` — a failed search is still a search."""
    src = inspect.getsource(router.claude_search)
    assert src.index("finally:") < src.index("await _log(user, meta)")
    assert "action=\"claude_search\"" in inspect.getsource(router._log)


def test_the_model_is_the_one_asked_for():
    assert cs.MODEL == "claude-sonnet-5-5"
