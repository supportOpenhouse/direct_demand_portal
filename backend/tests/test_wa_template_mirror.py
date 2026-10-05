"""The template form's client-side checks must decide exactly as the server does.

frontend/src/lib/api.ts `templateVars` / `isGupshupTemplateId` mirror `variable_count` / `GUPSHUP_ID_RE` in
app/services/wa_templates.py, so the form can say "slots skip a number" before a round trip. The slot rule already
changed once while this feature was built (slots must now FIRST APPEAR in order), and a client that is looser than the
server shows "Detected 2 variables" and an enabled Save for a body the server then refuses.

Both sides read ONE table, frontend/scripts/wa-template-cases.json:
  - this file runs every case through the real server functions;
  - `node frontend/scripts/check-wa-templates.mjs` runs the same cases through the real api.ts.
So one side changing without the other fails a check. To change a rule: change both sides and the table.
"""
import json
from pathlib import Path

import pytest

from app.services.wa_templates import GUPSHUP_ID_RE, variable_count

CASES_JSON = Path(__file__).parents[2] / "frontend" / "scripts" / "wa-template-cases.json"
CASES = json.loads(CASES_JSON.read_text(encoding="utf-8"))


def _slots(body: str) -> int:
    """What the form calls templateVars: the slot count, or -1 when the server refuses the body."""
    try:
        return variable_count(body)
    except ValueError:
        return -1


@pytest.mark.parametrize(("body", "n"), CASES["vars"])
def test_the_server_counts_slots_as_the_table_says(body, n):
    assert _slots(body) == n


@pytest.mark.parametrize(("value", "ok"), CASES["ids"])
def test_the_server_accepts_ids_as_the_table_says(value, ok):
    # normalize_template strips the id and then fullmatches; the client trims and tests the same shape
    assert bool(GUPSHUP_ID_RE.fullmatch(value.strip())) is ok


def test_the_table_is_not_one_sided():
    """A table that only ever says yes (or only ever no) would let either side drift unnoticed."""
    assert any(n >= 0 for _, n in CASES["vars"]) and any(n == -1 for _, n in CASES["vars"])
    assert any(ok for _, ok in CASES["ids"]) and any(not ok for _, ok in CASES["ids"])


def test_the_table_still_pins_the_rule_that_already_drifted():
    """The first-appearance order rule landed AFTER the client was written; keep it in the table."""
    vars_ = {body: n for body, n in CASES["vars"]}
    assert vars_["{{2}} {{1}}"] == -1
    assert vars_["{{1}} {{3}} {{2}}"] == -1
    assert vars_["{{1}} {{2}} {{1}}"] == 2
