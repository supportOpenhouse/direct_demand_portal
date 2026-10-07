"""Several societies per lead (spec docs/superpowers/specs/2026-10-07-lead-societies-design.md)."""
import pytest
from pydantic import BaseModel, ValidationError

from app.services.normalize import Societies, clean_societies


class _M(BaseModel):
    societies: Societies = []


def test_blanks_go_and_case_variants_keep_the_first_spelling():
    assert clean_societies(["ATS Pristine", " ats pristine ", "", "  ", "Gaur City 6"]) == \
        ["ATS Pristine", "Gaur City 6"]


def test_none_is_an_empty_list():
    assert clean_societies(None) == []


def test_the_model_cleans_what_it_is_given():
    assert _M(societies=[" A ", "a", "B"]).societies == ["A", "B"]


def test_too_long_or_too_many_is_refused_not_truncated():
    with pytest.raises(ValidationError):
        _M(societies=["x" * 201])
    with pytest.raises(ValidationError):
        _M(societies=[f"S{i}" for i in range(51)])


# --- Part A: Q4 == Q7, one column ------------------------------------------------

from sqlalchemy.dialects import postgresql  # noqa: E402

from app.models import Lead  # noqa: E402
from app.routers.leads import SourceDataPatch, _lead_row, shortlist_upsert  # noqa: E402


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_broker_societies_is_gone_everywhere():
    """Q4 is Q7: one column, lead_confirmed_data.shortlisted_societies."""
    from app.migrations import _ADD_COLUMNS
    assert "broker_societies" not in Lead.__table__.columns
    assert all(col != "broker_societies" for _, col, _ in _ADD_COLUMNS)
    assert "broker_societies" not in SourceDataPatch.model_fields


def test_the_shortlist_upsert_touches_only_that_column_and_reads_the_old_value_first():
    sql = _sql(shortlist_upsert("00000000-0000-0000-0000-000000000000", ["A"]))
    assert "ON CONFLICT (lead_id) DO UPDATE SET shortlisted_societies = excluded.shortlisted_societies" in sql
    set_clause = sql.split("DO UPDATE SET", 1)[1].split("RETURNING", 1)[0]
    assert set_clause.count("=") == 1, "a broker-card save must not rewrite the confirm form's answers"
    # an ALIASED subselect = the pre-statement snapshot, not the row just written
    assert "FROM lead_confirmed_data AS prev" in sql.split("RETURNING", 1)[1]


# --- Part B: scripts/24 — the database change ------------------------------------

import importlib.util  # noqa: E402
from pathlib import Path  # noqa: E402

_SCRIPT = Path(__file__).parents[1] / "scripts" / "24_lead_societies.py"
_spec = importlib.util.spec_from_file_location("lead_societies_script", _SCRIPT)
s24 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s24)


def test_the_column_matches_sources_shape():
    assert "ADD COLUMN IF NOT EXISTS societies TEXT[] NOT NULL DEFAULT '{}'" in s24.ADD_COLUMN
    col = Lead.__table__.columns["societies"]
    assert not col.nullable and col.server_default is not None


def test_the_fill_trigger_fires_before_the_merge_trigger():
    """Same-event triggers fire by NAME. The merge trigger reads NEW.societies, so the
    fill trigger has to have run first."""
    assert "leads_fill_societies" < "leads_merge_source"
    assert "CREATE TRIGGER leads_fill_societies" in s24.FILL_TRIGGER
    # only when one of the two is written — the dialer updates leads constantly
    assert "BEFORE INSERT OR UPDATE OF society, societies ON leads" in s24.FILL_TRIGGER


def test_societies_wins_and_society_always_follows_it():
    body = s24.FILL_FUNCTION
    assert body.index("NEW.societies IS DISTINCT FROM OLD.societies") < \
        body.index("NEW.society IS DISTINCT FROM OLD.society"), "societies is checked first"
    assert "NEW.society := NEW.societies[1];" in body
    # an insert only fills an EMPTY list — new code's own list is never overwritten
    assert "cardinality(NEW.societies) = 0 AND coalesce(btrim(NEW.society), '') <> ''" in body


def test_every_existing_society_is_backfilled_and_checked():
    assert "SET societies = ARRAY[btrim(society)]" in s24.BACKFILL
    assert "cardinality(societies) = 0" in s24.BACKFILL
    # the snapshot is taken BEFORE anything changes, and VERIFY checks it, not the
    # trigger-rewritten society column
    assert "CREATE TEMP TABLE _before" in s24.SNAPSHOT and "ON COMMIT DROP" in s24.SNAPSHOT
    assert "FROM _before" in s24.VERIFY
    for k in ("lost", "merge_missing", "out_of_step"):
        assert f"AS {k}" in s24.VERIFY


def test_past_merges_append_without_case_duplicates():
    sql = s24.APPEND_PAST_MERGES
    assert "a.action = 'lead_repeat'" in sql
    assert "lower(btrim(e)) = lower(x.society)" in sql
    assert "l.id::text = x.lead_id" in sql, "cast the uuid to text, never entity_id to uuid"


def test_the_merge_trigger_appends_case_insensitively():
    assert "lower(btrim(e)) = lower(btrim(s))" in s24.MERGE_APPEND
    assert "unnest(NEW.societies)" in s24.MERGE_APPEND


def test_the_merge_patch_applies_once_and_refuses_drift():
    live = "UPDATE leads SET sources = x,\n           " + s24.MERGE_ANCHOR + "\n           name = y"
    patched = s24.patched_merge_body(live)
    assert patched.count(s24.MERGE_APPEND) == 1
    assert s24.patched_merge_body(patched) is None, "re-running is a no-op"
    with pytest.raises(SystemExit):
        s24.patched_merge_body("UPDATE leads SET sources = x")  # anchor gone = hand-edited


def test_scripts_07_documents_the_live_merge_trigger():
    src = (Path(__file__).parents[1] / "scripts" / "07_lead_sources.sql").read_text()
    assert "unnest(NEW.societies)" in src


# --- writers take `societies` ------------------------------------------------------

import inspect  # noqa: E402

from app.routers import gupshup, huvo_calls  # noqa: E402
from app.routers import leads as leads_router  # noqa: E402


def test_every_create_and_edit_model_takes_a_cleaned_list():
    for model in (leads_router.NewLead, leads_router.SourceDataPatch,
                  gupshup.CreateLeadRequest, huvo_calls.HuvoLeadRequest):
        assert "society" not in model.model_fields, model.__name__
        assert "societies" in model.model_fields, model.__name__
    m = leads_router.NewLead(name="A", phone="9876543210", societies=[" X ", "x"])
    assert m.societies == ["X"]


def test_unticking_every_society_saves_an_empty_list_not_null():
    """societies is NOT NULL — the patch loop's `val or None` would turn [] into NULL."""
    src = inspect.getsource(leads_router.patch_source_data)
    assert "isinstance(val, list)" in src
    assert leads_router.SourceDataPatch(societies=[]).societies == []


def test_the_inserts_write_societies():
    for fn, needle in ((leads_router.create_lead, "societies=payload.societies"),
                       (gupshup.gupshup_create_lead, '"societies": req.societies'),
                       (huvo_calls.huvo_create_lead, '"societies": req.societies')):
        src = inspect.getsource(fn)
        assert needle in src, fn.__name__
        assert '"society"' not in src and "society=" not in src, fn.__name__


# --- readers use `societies` -------------------------------------------------------

import re  # noqa: E402

from app.routers import dialer as dialer_router  # noqa: E402
from app.routers import live_calls  # noqa: E402
from app.services import matching  # noqa: E402
from app.services.dialer import compile_rules  # noqa: E402


class _Row(dict):
    def __missing__(self, key):
        return None


def test_the_lead_payload_sends_the_list_and_never_the_old_key():
    out = _lead_row(_Row(id="x", societies=["A", "B"], society="A"))
    assert out["societies"] == ["A", "B"] and "society" not in out
    assert _lead_row(_Row(id="x"))["societies"] == []


async def test_matching_uses_every_society(monkeypatch):
    seen = {}

    async def fake_build(city, societies, *rest):
        seen["societies"] = societies
        return {}

    monkeypatch.setattr(matching, "build_requirement", fake_build)
    await matching.lead_requirement({"societies": ["A", "B"], "city": "Noida"}, None)
    assert seen["societies"] == ["A", "B"]


def test_a_dialer_society_rule_is_an_array_overlap():
    sql, params = compile_rules({"type": "condition", "field": "society", "op": "IN", "value": ["A", "B"]})
    assert sql.startswith("l.societies && CAST(ARRAY[") and set(params.values()) == {"A", "B"}
    sql, _ = compile_rules({"type": "condition", "field": "society", "op": "NOT IN", "value": ["A"]})
    assert sql.startswith("NOT (l.societies && CAST(ARRAY[")


def test_dialer_society_options_unnest_the_list():
    assert "unnest(societies)" in dialer_router.SOCIETY_OPTIONS
    assert "society" not in dialer_router._OPTION_COLUMNS


def test_display_queries_flatten_the_list():
    for q in (live_calls._NOW_CALLING.text, live_calls._COMPLETED_TODAY.text, live_calls._UPCOMING):
        assert not re.search(r"l\.society\b", q)
        assert "array_to_string(l.societies, ', ') AS society" in q
    assert "array_to_string(l.societies, ', ') AS society" in inspect.getsource(dialer_router)


def test_script_24_names_the_host_not_just_the_database():
    """Every Neon branch is `neondb` — the host is what tells prod from a stale branch."""
    src = inspect.getsource(s24.main)
    assert "urlparse(" in src and ".hostname" in src
