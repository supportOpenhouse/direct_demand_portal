"""Server-side sort for the three server-paged lists (Call Log + Dialer history, Huvo calls,
Activity Logs). The browser only holds one page, so a column sort must be an ORDER BY —
built from a WHITELIST: a key the page sends maps to SQL written here, never to raw input."""
import inspect
import re
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.sorting import order_by
from app.routers import activity, bonvoice, huvo_calls

PAGES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages"


def test_no_sort_keeps_the_default_order():
    assert order_by(None, None, {"when": "a.created_at"}, "a.created_at DESC") == " ORDER BY a.created_at DESC"


def test_a_sort_is_whitelisted_with_blanks_last_and_a_stable_tiebreak():
    sql = order_by("who", "desc", {"who": "COALESCE(a.actor_name, a.actor_email)"}, "a.created_at DESC")
    assert sql == " ORDER BY COALESCE(a.actor_name, a.actor_email) DESC NULLS LAST, a.created_at DESC"
    assert order_by("who", None, {"who": "x"}, "d").startswith(" ORDER BY x ASC NULLS LAST")


@pytest.mark.parametrize("sort, dir_", [("a.id; DROP TABLE leads", "asc"), ("who", "sideways")])
def test_anything_not_whitelisted_is_a_422(sort, dir_):
    with pytest.raises(HTTPException) as e:
        order_by(sort, dir_, {"who": "x"}, "d")
    assert e.value.status_code == 422


def _page_sort_keys(*names):
    keys = set()
    for n in names:
        keys |= set(re.findall(r'sortKey="(\w+)"', (PAGES / n).read_text()))
    return keys


@pytest.mark.parametrize("sorts, pages", [
    (bonvoice.CALL_LOG_SORTS, ("CallLog.tsx", "DialerPrevious.tsx")),
    (huvo_calls.HUVO_SORTS, ("HuvoCalls.tsx",)),
    (activity.ACTIVITY_SORTS, ("Logs.tsx",)),
])
def test_every_column_a_page_sorts_is_one_the_server_knows(sorts, pages):
    """Both directions: a header the server can't sort is a 422 on click; a key the server
    knows but no header sends is a column someone forgot to make sortable."""
    for p in pages:
        assert _page_sort_keys(p) == set(sorts), p


@pytest.mark.parametrize("fn", [bonvoice.call_log, huvo_calls.huvo_calls, activity.list_activity])
def test_the_list_endpoints_take_sort_and_dir(fn):
    params = inspect.signature(fn).parameters
    assert "sort" in params and params["sort_dir"].default.alias == "dir"
