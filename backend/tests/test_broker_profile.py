"""The "Broker & buyer profile" card above "Lead data confirmed on call".

Four answers on `leads`, written through PATCH /leads/{id}/source-data one pick at a
time. The dropdowns offer a fixed list; the server refuses anything else. Q4 (societies
shortlisted with the broker) is Q7's column and has its own endpoint
(tests/test_lead_societies.py).
"""
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.routers.leads import BROKER_OPTIONS, SourceDataPatch, _lead_row

LEADS_TS = Path(__file__).parents[2] / "frontend" / "src" / "lib" / "leads.ts"
FIELDS = ("broker_count", "broker_search_since", "buyer_property_type", "buyer_profession")


def test_the_frontend_offers_exactly_the_answers_the_server_accepts():
    """A choice in the dropdown the server doesn't know is a 422 on every pick."""
    block = LEADS_TS.read_text().split("export const BROKER_OPTIONS", 1)[1].split("};", 1)[0]
    ts = {k: re.findall(r'"([^"]+)"', v) for k, v in re.findall(r"(\w+):\s*\[([^\]]*)\]", block)}
    assert ts == {k: list(v) for k, v in BROKER_OPTIONS.items()}


@pytest.mark.parametrize("field", FIELDS)
def test_an_answer_off_the_list_is_refused(field):
    with pytest.raises(ValidationError):
        SourceDataPatch(**{field: "banana"})


@pytest.mark.parametrize("field", FIELDS)
def test_every_listed_answer_and_blank_are_accepted(field):
    for v in ("", *BROKER_OPTIONS[field]):  # blank = the dropdown's "Select…", clears it
        assert getattr(SourceDataPatch(**{field: v}), field) == v


def test_the_lead_payload_carries_the_answers():
    class Row(dict):
        def __missing__(self, key):
            return None

    row = Row(id="x", broker_count="2", broker_search_since="1 month",
              buyer_property_type="Open to all",
              buyer_profession="Salaried")
    out = _lead_row(row)
    for k in FIELDS:
        assert out[k] == row[k], k
