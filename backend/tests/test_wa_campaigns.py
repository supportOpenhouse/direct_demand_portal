"""WhatsApp template campaigns — schema rules and the SQL rules the service encodes.
Spec: docs/superpowers/specs/2026-09-29-whatsapp-template-campaigns-design.md"""
import base64
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import models
from app.config import get_settings
from app.routers import wa_campaigns as r
from app.services import activity
from app.services import wa_campaigns as svc
from app.services.wa_recipients import Candidate


def test_the_four_tables_exist_with_their_keys():
    t = models.Base.metadata.tables
    for name in ("wa_templates", "wa_campaigns", "wa_campaign_recipients", "wa_auto_campaigns"):
        assert name in t, name
    # Check for partial unique index on gupshup_template_id (active only)
    wa_t_indexes = {idx.name: idx for idx in t["wa_templates"].indexes}
    assert "uq_wa_templates_active_gupshup_id" in wa_t_indexes, "partial unique index on gupshup_template_id"
    idx = wa_t_indexes["uq_wa_templates_active_gupshup_id"]
    assert idx.unique, "index should be unique"
    assert str(idx.dialect_options["postgresql"]["where"]) == "active", "index only applies to active=true rows"
    rec = t["wa_campaign_recipients"]
    uniques = {tuple(sorted(c.name for c in u.columns)) for u in rec.constraints
               if u.__class__.__name__ == "UniqueConstraint"}
    assert ("campaign_id", "phone10") in uniques, "one row per number per campaign"
    camp = t["wa_campaigns"]
    uniques = {tuple(sorted(c.name for c in u.columns)) for u in camp.constraints
               if u.__class__.__name__ == "UniqueConstraint"}
    assert ("auto_campaign_id", "run_slot") in uniques, "one auto run per slot"
    # Foreign keys on repeat_of and seed_campaign_id
    assert {fk.target_fullname for fk in camp.c.repeat_of.foreign_keys} == {"wa_campaigns.id"}, "repeat_of → wa_campaigns"
    auto = t["wa_auto_campaigns"]
    assert {fk.target_fullname for fk in auto.c.seed_campaign_id.foreign_keys} == {"wa_campaigns.id"}, "seed_campaign_id → wa_campaigns"
    # Server defaults on all id columns
    for table_name in ("wa_templates", "wa_campaigns", "wa_campaign_recipients", "wa_auto_campaigns"):
        assert t[table_name].c.id.server_default is not None, f"{table_name}.id missing server_default"


def test_template_app_config_reports_what_is_missing(monkeypatch):
    from app.config import get_settings
    s = get_settings()
    for k in ("GUPSHUP_TEMPLATE_API_KEY", "GUPSHUP_TEMPLATE_SOURCE_NUMBER", "GUPSHUP_TEMPLATE_APP_NAME"):
        monkeypatch.setattr(s, k, "")
    assert not s.gupshup_template_configured
    assert s.gupshup_template_missing == [
        "GUPSHUP_TEMPLATE_API_KEY", "GUPSHUP_TEMPLATE_SOURCE_NUMBER", "GUPSHUP_TEMPLATE_APP_NAME"]
    monkeypatch.setattr(s, "GUPSHUP_TEMPLATE_API_KEY", "k")
    monkeypatch.setattr(s, "GUPSHUP_TEMPLATE_SOURCE_NUMBER", "919999999999")
    monkeypatch.setattr(s, "GUPSHUP_TEMPLATE_APP_NAME", "OH Templates")
    assert s.gupshup_template_configured and s.gupshup_template_missing == []


def test_recipients_carry_their_position_in_the_list():
    """Ids are random uuids, so without a stored position a list comes back in an arbitrary order
    (a pasted [50,10,40,20,30] came back [40,30,20,50,10]) — and under the daily cap, order decides who is messaged."""
    col = models.WaCampaignRecipient.__table__.c.position
    assert not col.nullable and col.default.arg == 0 and str(col.server_default.arg) == "0"


# ── Task 5: preview + create draft ────────────────────────────────────────────────
# The SQL needs a live Postgres, so the first half asserts the RULES it encodes (the
# test_wa_assign.py pattern) — each pin is a FULL predicate, because a pin on a fragment
# survives the mutant that flips the rest of it. The second half runs the Python around
# the SQL against a fake connection that answers from canned rows and records every statement.

def test_exclusions_cover_the_five_reasons():
    sql = svc.EXCLUDE_SQL.text
    for reason in ("'opted_out'", "'rejected'", "'is_lead'", "'no_whatsapp'", "'cooldown'"):
        assert reason in sql, reason


def test_an_unreadable_upload_says_so_instead_of_500ing():
    with pytest.raises(ValueError, match="couldn't read that file"):
        svc.read_upload("list.xlsx", base64.b64encode(b"not a zip").decode())
    with pytest.raises(ValueError, match="couldn't read that file"):
        svc.read_upload("list.csv", "%%% not base64 %%%")
    good = base64.b64encode(b"Phone\n9876543210\n").decode()
    with pytest.raises(ValueError, match="couldn't read that file"):  # junk around real base64: refuse, don't skim it
        svc.read_upload("list.csv", "%%%" + good)
    assert svc.read_upload("list.csv", good) == (["Phone"], [["9876543210"]])


def test_create_refuses_an_unpadded_or_backwards_send_window():
    """The send loop compares HH:MM as TEXT — '9:00' would sort after '10:00' and never send."""
    base = {"template_id": str(uuid.uuid4()), "source": "paste", "name": "Diwali"}
    assert r.CreateIn(**base).send_window_start == "10:00"
    for bad in ({"send_window_start": "9:00"}, {"send_window_end": "24:00"},
                {"send_window_start": "19:00", "send_window_end": "10:00"}, {"name": "   "}):
        with pytest.raises(ValidationError):
            r.CreateIn(**{**base, **bad})  # merged, not `**base, **bad`: `name` is in both → TypeError


@pytest.mark.parametrize("bad", [{"phone_col": -1}, {"name_col": -1}, {"var_cols": [-9]}, {"var_cols": [0, -1]}])
def test_column_indices_cannot_be_negative(bad):
    """A negative index reads from the row's END, and -9 raises IndexError (which a broad `except LookupError`
    turned into a misleading 404)."""
    with pytest.raises(ValidationError):
        r.PreviewIn(template_id=uuid.uuid4(), source="paste", **bad)
    ok = r.PreviewIn(template_id=uuid.uuid4(), source="paste", phone_col=0, name_col=0, var_cols=[0, None, 3])
    assert (ok.phone_col, ok.name_col, ok.var_cols) == (0, 0, [0, None, 3])


def test_a_campaign_name_and_a_paste_are_length_capped():
    base = {"template_id": str(uuid.uuid4()), "source": "paste"}
    assert r.CreateIn(**base, name="x" * 120).name == "x" * 120
    with pytest.raises(ValidationError):
        r.CreateIn(**base, name="x" * 121)
    assert len(r.PreviewIn(**base, paste="x" * 2_000_000).paste) == 2_000_000
    with pytest.raises(ValidationError):
        r.PreviewIn(**base, paste="x" * 2_000_001)


def test_the_lead_check_reads_the_leads_table_once():
    """Not a regex over every lead for every uploaded phone (a correlated EXISTS in a CASE)."""
    sql = svc.EXCLUDE_SQL.text
    assert sql.count("FROM leads") == 1 and "LEFT JOIN lp ON lp.phone10 = p.phone10" in sql


def test_no_whatsapp_matches_gupshups_code_never_its_reason_text():
    """Gupshup spells 1002's reason three ways (contract §3.5/§8) — the code is the only stable key."""
    sql = svc.EXCLUDE_SQL.text
    assert "split_part(r.error, ':', 1) = '1002'" in sql
    assert "ILIKE" not in sql


def test_no_whatsapp_needs_a_failed_send_not_just_any_row_carrying_that_code():
    """Pinned INSIDE the no_whatsapp clause: a recipient whose send later recovered must not blacklist the number."""
    clause = re.search(r"WHEN EXISTS \((.*?)\) THEN 'no_whatsapp'", svc.EXCLUDE_SQL.text, re.S).group(1)
    assert "r.status = 'failed'" in clause and "split_part(r.error, ':', 1) = '1002'" in clause


def test_cooldown_ignores_the_family_of_the_list_being_repeated():
    """Repeating a list must not be blocked by its own source campaign(s) (spec §4.4, §10)."""
    sql = svc.EXCLUDE_SQL.text
    assert "NOT (r.campaign_id = ANY(CAST(:ignore_campaigns AS uuid[])))" in sql
    # the FULL predicate: a send INSIDE the window blocks; flipping `>` would block everything outside it
    assert "r.sent_at > (now() - make_interval(days => :cooldown_days))" in sql


def test_wa_contacts_source_is_non_leads_and_not_excluded_tags():
    sql = svc.WA_CONTACTS_SQL.text
    assert "NOT EXISTS" in sql and "FROM leads l" in sql
    assert "c.tag NOT IN ('rejected', 'opted_out')" in sql, "rejected / opted-out contacts are left out"
    assert "WHERE m.direction = 'in'" in sql, "people who wrote to us — not numbers we only ever messaged"


def test_wa_contacts_come_back_newest_first_with_their_full_stored_phone():
    """build() needs the FULL phone — pre-slicing +44 7911 123456 to ten digits makes a stranger's Indian mobile —
    and the order decides who is messaged first under the daily cap (DISTINCT ON forces ORDER BY number, so the
    newest-first sort has to wrap it)."""
    sql = svc.WA_CONTACTS_SQL.text
    assert "SELECT DISTINCT ON (right(m.phone, 10)) m.phone AS phone, m.name, m.created_at AS last_at" in sql
    # the INNER order picks which message DISTINCT ON keeps per number: DESC = the newest (ASC would hand back
    # each number's OLDEST message for its phone, name and last_at)
    assert "ORDER BY right(m.phone, 10), m.created_at DESC" in sql
    assert re.search(r"\)\s*\w+\s+ORDER BY last_at DESC, phone\s*$", sql.strip()), "outer ORDER BY, after the DISTINCT ON"


def test_repeat_non_responders_drops_anyone_who_replied_after_their_send():
    sql = svc.REPEAT_SQL.text
    assert ":mode = 'everyone' OR NOT EXISTS" in sql, "everyone, OR only those with no later reply (AND would return nobody)"
    assert "m.direction = 'in'" in sql and "m.created_at > r.sent_at" in sql


def test_a_repeat_copies_skipped_rows_so_every_build_re_decides_them():
    """D-I2: a skip is decided again at every build (spec §5.1, §7.2). Dropping skipped rows turned ONE cooldown
    skip into removal from every later run of an auto campaign. Only the two skips that can't lapse are dropped —
    with COALESCE, because skip_reason is NULL on every row that wasn't skipped and NOT (NULL) would drop them all."""
    sql = svc.REPEAT_SQL.text
    assert "'skipped'" not in sql, "skipped rows must be copied"
    assert "AND NOT COALESCE(r.skip_reason IN ('is_lead', 'no_whatsapp'), false)" in sql


def test_a_repeat_never_resends_to_numbers_refused_for_good():
    sql = svc.REPEAT_SQL.text
    assert "split_part(r.error, ':', 1) IN ('1002', '131026', '131050', '1012')" in sql
    assert "ILIKE" not in sql, "match Gupshup's code, never its reason text"


def test_a_failed_row_with_no_error_text_is_still_repeated():
    """NOT (failed AND NULL) is NULL and WHERE reads NULL as false — such a recipient silently vanished
    from the repeat (found by running the query: a failed row with error IS NULL came back missing)."""
    assert "COALESCE(split_part(r.error, ':', 1) IN ('1002', '131026', '131050', '1012'), false)" in svc.REPEAT_SQL.text


def test_a_repeat_keeps_the_lists_order():
    assert "ORDER BY r.position, r.id" in svc.REPEAT_SQL.text


def test_the_repeat_family_walks_up_to_the_root_and_down_to_every_descendant():
    """A manual chain A → B → C repeated from B must also forgive A's sends, and a sibling's — the whole tree."""
    sql = svc.REPEAT_FAMILY_SQL.text
    assert "WITH RECURSIVE up AS" in sql and "JOIN up ON c.id = up.repeat_of" in sql, "up: source → … → the root"
    assert "SELECT id FROM up WHERE repeat_of IS NULL" in sql and "JOIN down ON c.repeat_of = down.id" in sql, \
        "down: every descendant of that root"


def test_the_walk_up_dedupes_so_a_cycle_in_repeat_of_ends_instead_of_looping_forever():
    """UNION (not UNION ALL) in `up` discards a row it has already produced, so a hand-made cycle (raw SQL only)
    terminates. `down` keeps UNION ALL: it only descends from a root, and a tree has no repeats to drop."""
    sql = svc.REPEAT_FAMILY_SQL.text
    assert re.search(r"WHERE id = :src\s+UNION\s+SELECT c\.id, c\.repeat_of FROM wa_campaigns c JOIN up", sql), \
        "`up` must be a plain UNION"
    assert re.search(r"SELECT id FROM up WHERE repeat_of IS NULL\s+UNION ALL\s+SELECT c\.id", sql), "`down` stays UNION ALL"


def test_reply_lookups_by_last_10_digits_are_indexed():
    import inspect
    from app import migrations
    src = inspect.getsource(migrations)
    assert "CREATE INDEX IF NOT EXISTS ix_wa_messages_phone10_created" in src
    assert "ON wa_messages (right(phone, 10), created_at)" in src


# ── the Python around the SQL, against a fake connection ──────────────────────────

class _Result:
    """Just enough of a SQLAlchemy Result: iterate it, or `.mappings().first()` / `.all()`."""

    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeConn:
    """Answers each query the service makes from canned rows and records every statement.
    A lookup can MISS: template=None / source_slots=None answer with no row."""

    def __init__(self, *, template=None, excluded=None, contacts=(), repeat=(), source_slots=2, family=None):
        self.template, self.excluded = template, excluded or {}
        self.contacts, self.repeat = list(contacts), list(repeat)
        self.source_slots, self.family = source_slots, family
        self.calls = []  # (statement, params)

    async def execute(self, stmt, params=None):
        self.calls.append((stmt, params))
        if stmt is svc.EXCLUDE_SQL:  # one (phone10, reason-or-NULL) row per distinct phone, like the SQL
            return _Result((p, self.excluded.get(p)) for p in dict.fromkeys(params["phones"]))
        if stmt is svc.WA_CONTACTS_SQL:
            return _Result(self.contacts)
        if stmt is svc.SOURCE_CAMPAIGN_SQL:  # the campaign being repeated + its template's slot count
            return _Result([] if self.source_slots is None
                           else [{"id": params["campaign_id"], "variable_count": self.source_slots}])
        if stmt is svc.REPEAT_FAMILY_SQL:  # the whole repeat tree (default: just the source)
            return _Result((u,) for u in (self.family if self.family is not None else [params["src"]]))
        if stmt is svc.REPEAT_SQL:
            return _Result(self.repeat)
        if self.template is not None and getattr(stmt, "is_select", False):  # the template lookup
            return _Result([self.template])
        return _Result([])


class _Ctx:
    def __init__(self, engine, kind):
        self.engine, self.kind = engine, kind

    async def __aenter__(self):
        return self.engine.conn

    async def __aexit__(self, exc_type, exc, tb):
        # begin() commits on a clean exit and rolls back on an exception; connect() commits nothing, ever
        self.engine.log.append((self.kind, "close" if self.kind == "connect"
                                else "rollback" if exc_type else "commit"))
        return False


class _FakeEngine:
    def __init__(self, conn):
        self.conn, self.log = conn, []

    def connect(self):
        return _Ctx(self, "connect")

    def begin(self):
        return _Ctx(self, "begin")


def _use(monkeypatch, conn):
    """Point the router at the fake — and keep a router test from ever opening a real
    connection (backend/.env is PRODUCTION). Returns the engine: `.conn` and `.log`."""
    engine = _FakeEngine(conn)
    monkeypatch.setattr(r, "_engine", lambda: engine)
    return engine


def _template(**over):
    return {"id": uuid.uuid4(), "active": True, "body": "Hi {{1}}, a flat in {{2}} for you",
            "variable_count": 2, "variable_defaults": [None, "Noida"], **over}


def _inserts(conn, table):
    return [(s, p) for s, p in conn.calls if getattr(getattr(s, "table", None), "name", None) == table]


def _lookups(conn):
    """The params of every exclusion query the service ran."""
    return [p for s, p in conn.calls if s is svc.EXCLUDE_SQL]


ADMIN = {"email": "admin@openhouse.in", "name": "Admin", "role": "admin"}
NOTHING = ("Nothing to send — no number in this list can be messaged "
           "(all invalid, duplicates, or skipped; see the preview for why)")


async def test_classify_gives_every_candidate_exactly_one_verdict():
    cands = [
        Candidate("9876543210", "Asha", ["Asha", "Noida"]),                         # clean
        Candidate("9876543211", "Ravi", ["Ravi", "Noida"]),                         # opted out
        Candidate(None, None, [None, None], "invalid_phone"),
        Candidate("9876543210", "Asha", ["Asha", "Noida"], "duplicate"),
        Candidate("9876543212", "Meera", ["Meera", None], "missing_variable"),
    ]
    camp = uuid.uuid4()
    conn = _FakeConn(excluded={"9876543211": "opted_out"})
    rows = await svc.classify(conn, cands, cooldown_days=3, ignore_campaigns=[camp])
    assert [(x["status"], x["reason"]) for x in rows] == [
        ("valid", None), ("skipped", "opted_out"), ("invalid", "invalid_phone"),
        ("duplicate", "duplicate"), ("invalid", "missing_variable")]
    [(stmt, params)] = conn.calls
    assert stmt is svc.EXCLUDE_SQL
    # only numbers that are still candidates are looked up; the ids go through as UUID objects
    assert params == {"phones": ["9876543210", "9876543211"], "cooldown_days": 3,
                      "ignore_campaigns": [camp], "skip_leads": True}


async def test_nothing_to_check_means_no_query():
    conn = _FakeConn()
    rows = await svc.classify(conn, [Candidate(None, None, [], "invalid_phone")], cooldown_days=7, ignore_campaigns=[])
    assert conn.calls == [] and rows[0]["status"] == "invalid"


async def test_paste_fills_slots_from_columns_then_template_defaults():
    conn = _FakeConn(template=_template())
    req = r.PreviewIn(template_id=uuid.uuid4(), source="paste", var_cols=[1],
                      paste="98765 43210, Asha\n9876543211\nnot a phone")
    cands, t, headers = await svc.candidates_for(conn, req)
    assert headers == [] and t["variable_count"] == 2
    assert [(c.phone10, c.variables, c.error) for c in cands] == [
        ("9876543210", ["Asha", "Noida"], None),                    # slot 2 falls back to the default
        ("9876543211", [None, "Noida"], "missing_variable"),        # no cell for slot 1, no default
        (None, [None, "Noida"], "invalid_phone")]


async def test_upload_reads_the_mapped_columns_and_hands_back_the_headers():
    csv_text = "Mobile,Name,City\n9876543210,Asha,Gurgaon\n+91 98765 43211,Ravi,\n"
    req = r.PreviewIn(template_id=uuid.uuid4(), source="upload", file_name="list.csv", phone_col=0, name_col=1,
                      var_cols=[1, 2], file_b64=base64.b64encode(csv_text.encode()).decode())
    cands, _, headers = await svc.candidates_for(_FakeConn(template=_template()), req)
    assert headers == ["Mobile", "Name", "City"]
    assert [(c.phone10, c.name, c.variables) for c in cands] == [
        ("9876543210", "Asha", ["Asha", "Gurgaon"]),
        ("9876543211", "Ravi", ["Ravi", "Noida"])]                  # blank City → the default


async def test_an_upload_is_read_off_the_event_loop(monkeypatch):
    """A 200k-row .xlsx blocked the loop for ~3 s — in the one process that also serves the webhooks and the dialer."""
    seen = {}

    def fake_read(file_name, file_b64):
        seen["thread"] = threading.get_ident()
        return ["Mobile"], [["9876543210"]]

    monkeypatch.setattr(svc, "read_upload", fake_read)
    req = r.PreviewIn(template_id=uuid.uuid4(), source="upload", file_name="l.csv", file_b64="x", var_cols=[None, None],
                      fixed=["a", "b"])
    cands, _, headers = await svc.candidates_for(_FakeConn(template=_template()), req)
    assert headers == ["Mobile"] and [c.phone10 for c in cands] == ["9876543210"]
    assert seen["thread"] != threading.get_ident(), "read_upload ran on the event loop's own thread"


async def test_wa_contacts_fill_a_slot_from_the_sender_name_or_a_fixed_value():
    contacts = [{"phone": "919876543210", "name": "Asha"}, {"phone": "919876543211", "name": None},
                {"phone": "447911123456", "name": "Gill"}]      # a UK number: refused, not sliced to ten digits
    conn = _FakeConn(template=_template(), contacts=contacts)
    req = r.PreviewIn(template_id=uuid.uuid4(), source="wa_contacts", var_cols=[1, None], fixed=[None, "Gurgaon"])
    cands, _, _ = await svc.candidates_for(conn, req)
    assert [(c.phone10, c.variables, c.error) for c in cands] == [
        ("9876543210", ["Asha", "Gurgaon"], None),
        ("9876543211", [None, "Gurgaon"], "missing_variable"),      # a sender with no name
        (None, ["Gill", "Gurgaon"], "invalid_phone")]               # 7911123456 would have been a stranger's number


async def test_repeat_copies_the_list_and_refills_slots_from_the_defaults():
    old = [{"phone10": "9876543210", "name": "Asha", "variables": ["Asha"]},               # short lists are padded
           {"phone10": "9876543211", "name": "Ravi", "variables": ["Ravi", "Gurgaon"]},
           {"phone10": "9876543212", "name": None, "variables": []}]
    src = uuid.uuid4()
    conn = _FakeConn(template=_template(), repeat=old)
    req = r.PreviewIn(template_id=uuid.uuid4(), source="repeat", repeat_of=src, repeat_mode="non_responders")
    cands, _, _ = await svc.candidates_for(conn, req)
    assert [(c.phone10, c.variables, c.error) for c in cands] == [
        ("9876543210", ["Asha", "Noida"], None),
        ("9876543211", ["Ravi", "Gurgaon"], None),
        ("9876543212", [None, "Noida"], "missing_variable")]
    [(_, params)] = [c for c in conn.calls if c[0] is svc.REPEAT_SQL]
    assert params == {"campaign_id": src, "mode": "non_responders"}


async def test_repeat_flattens_a_default_that_fills_an_empty_slot():
    """A default with a newline, a tab or 5+ spaces would reach Meta as-is and fail every row (error 132018)."""
    old = [{"phone10": "9876543210", "name": "Asha", "variables": ["Asha", None]},
           {"phone10": "9876543211", "name": "Ravi", "variables": ["Ravi", ""]}]
    conn = _FakeConn(template=_template(variable_defaults=[None, "Sector 62,\n     Noida\t(ext)"]), repeat=old)
    cands, _, _ = await svc.candidates_for(conn, r.PreviewIn(template_id=uuid.uuid4(), source="repeat",
                                                             repeat_of=uuid.uuid4()))
    assert [c.variables for c in cands] == [["Asha", "Sector 62, Noida (ext)"], ["Ravi", "Sector 62, Noida (ext)"]]
    assert [c.error for c in cands] == [None, None]


@pytest.mark.parametrize("sent_with, chosen, said", [(2, 1, "2 variables"), (1, 2, "1 variable"), (0, 2, "0 variables")])
async def test_a_repeat_with_a_different_slot_count_is_refused(sent_with, chosen, said):
    """Padding or truncating by position would shift every variable into the wrong slot (spec §5.1: a different
    template is allowed only 'if the slot count matches')."""
    body = " ".join(f"{{{{{i + 1}}}}}" for i in range(chosen))
    template = _template(body=body, variable_count=chosen, variable_defaults=[None] * chosen)
    old = [{"phone10": "9876543210", "name": "Asha", "variables": ["Asha"] * sent_with}]
    conn = _FakeConn(template=template, source_slots=sent_with, repeat=old)
    req = r.PreviewIn(template_id=uuid.uuid4(), source="repeat", repeat_of=uuid.uuid4())
    with pytest.raises(ValueError) as e:
        await svc.candidates_for(conn, req)
    assert str(e.value) == (f"That list was sent with a template that has {said} — "
                            f"pick a template with {sent_with}, or upload the list again")
    assert [c for c in conn.calls if c[0] is svc.REPEAT_SQL] == [], "refused before the list is read"


async def test_the_same_slot_count_is_fine_even_with_a_different_template():
    conn = _FakeConn(template=_template(), source_slots=2,
                     repeat=[{"phone10": "9876543210", "name": "Asha", "variables": ["Asha", "Gurgaon"]}])
    cands, _, _ = await svc.candidates_for(conn, r.PreviewIn(template_id=uuid.uuid4(), source="repeat",
                                                             repeat_of=uuid.uuid4()))
    assert [c.variables for c in cands] == [["Asha", "Gurgaon"]]


async def test_a_repeat_with_no_source_campaign_is_refused_before_any_query():
    """create has no router-level guard like preview's: without this it saved an EMPTY draft."""
    with pytest.raises(ValueError, match="pick the campaign"):
        await svc.candidates_for(None, r.PreviewIn(template_id=uuid.uuid4(), source="repeat"))  # conn=None: must not look


async def test_an_unknown_template_is_not_found():
    with pytest.raises(svc.NotFound):
        await svc.candidates_for(_FakeConn(template=None), r.PreviewIn(template_id=uuid.uuid4(), source="paste"))


async def test_an_unknown_campaign_to_repeat_is_not_found():
    """It used to be an FK error (a 500) on create and an empty 200 on preview."""
    conn = _FakeConn(template=_template(), source_slots=None)
    with pytest.raises(svc.NotFound, match="campaign to repeat"):
        await svc.candidates_for(conn, r.PreviewIn(template_id=uuid.uuid4(), source="repeat", repeat_of=uuid.uuid4()))
    assert [c for c in conn.calls if c[0] is svc.REPEAT_SQL] == []


def test_not_found_is_not_a_lookup_error():
    """IndexError and KeyError ARE LookupErrors — a router that catches LookupError dresses a real bug up as a 404."""
    assert issubclass(svc.NotFound, Exception) and not issubclass(svc.NotFound, LookupError)


async def test_create_draft_saves_valid_and_skipped_numbers_and_drops_the_rest():
    tid = uuid.uuid4()
    conn = _FakeConn(template=_template(id=tid), excluded={"9876543211": "cooldown"})
    req = r.CreateIn(template_id=tid, source="paste", name="  Diwali push ", name_col=1, var_cols=[1],
                     paste="9876543210, Asha\n9876543211, Ravi\nnot a phone\n9876543210, Asha again")
    cid = await svc.create_draft(conn, req, ADMIN)

    [(stmt, _)] = _inserts(conn, "wa_campaigns")
    values = stmt.compile().params
    assert (values["id"], values["name"], values["status"], values["source"]) == (cid, "Diwali push", "draft", "paste")
    assert values["repeat_of"] is None and values["created_by"] == "admin@openhouse.in"
    assert (values["send_window_start"], values["send_window_end"], values["rate_per_minute"]) == ("10:00", "19:00", 30)

    [(_, rows)] = _inserts(conn, "wa_campaign_recipients")
    assert [(x["phone10"], x["status"], x["skip_reason"], x["variables"]) for x in rows] == [
        ("9876543210", "queued", None, ["Asha", "Noida"]),
        ("9876543211", "skipped", "cooldown", ["Ravi", "Noida"])], "the invalid and the duplicate row are shown, not saved"
    assert {x["campaign_id"] for x in rows} == {cid}

    [(_, log_rows)] = [(s, p) for s, p in conn.calls if s is activity._INSERT]
    assert (log_rows[0]["action"], log_rows[0]["entity_type"], log_rows[0]["entity_id"]) == (
        "wa_campaign_created", "wa_campaign", str(cid))
    assert json.loads(log_rows[0]["metadata"]) == {"name": "Diwali push", "source": "paste", "queued": 1, "skipped": 1}
    assert [x["ignore_campaigns"] for x in _lookups(conn)] == [[]], "a fresh list has no source campaign to ignore"


async def test_recipients_keep_list_order():
    """Pasted [50,10,40,20,30] came back [40,30,20,50,10]: ids are random uuids, so the order has to be stored.
    Skipped rows keep their place; a row that isn't saved doesn't use up a position."""
    tid = uuid.uuid4()
    conn = _FakeConn(template=_template(id=tid), excluded={"9876543240": "cooldown"})
    paste = "9876543250, A\n9876543210, B\nnot a phone\n9876543240, C\n9876543220, D\n9876543230, E"
    await svc.create_draft(conn, r.CreateIn(template_id=tid, source="paste", name="x", var_cols=[1], paste=paste), ADMIN)
    [(_, rows)] = _inserts(conn, "wa_campaign_recipients")
    assert [(x["phone10"], x["position"]) for x in rows] == [
        ("9876543250", 0), ("9876543210", 1), ("9876543240", 2), ("9876543220", 3), ("9876543230", 4)]


async def test_a_repeat_is_saved_with_its_source_and_not_blocked_by_it():
    src, tid = uuid.uuid4(), uuid.uuid4()
    conn = _FakeConn(template=_template(id=tid),
                     repeat=[{"phone10": "9876543210", "name": "Asha", "variables": ["Asha", "Noida"]}])
    await svc.create_draft(conn, r.CreateIn(template_id=tid, source="repeat", repeat_of=src, name="Again"), ADMIN)
    assert [x["ignore_campaigns"] for x in _lookups(conn)] == [[src]]
    [(stmt, _)] = _inserts(conn, "wa_campaigns")
    assert stmt.compile().params["repeat_of"] == src


async def test_only_a_repeat_records_a_source_campaign():
    tid = uuid.uuid4()
    conn = _FakeConn(template=_template(id=tid))
    req = r.CreateIn(template_id=tid, source="paste", repeat_of=uuid.uuid4(), name="x", var_cols=[1],
                     paste="9876543210, Asha")
    await svc.create_draft(conn, req, ADMIN)
    [(stmt, _)] = _inserts(conn, "wa_campaigns")
    assert stmt.compile().params["repeat_of"] is None


async def test_a_stray_repeat_of_on_a_fresh_list_ignores_no_cooldown():
    """It used to lift that campaign's cooldown even for a paste or an upload."""
    tid, stray = uuid.uuid4(), uuid.uuid4()
    conn = _FakeConn(template=_template(id=tid), family=[stray])
    req = r.CreateIn(template_id=tid, source="paste", repeat_of=stray, name="x", var_cols=[1], paste="9876543210, Asha")
    await svc.create_draft(conn, req, ADMIN)
    assert [x["ignore_campaigns"] for x in _lookups(conn)] == [[]]
    assert [c for c in conn.calls if c[0] is svc.REPEAT_FAMILY_SQL] == [], "the family is never even looked up"


async def test_ignore_for_gives_the_whole_tree_for_a_repeat_and_nothing_otherwise():
    root, mid, leaf = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conn = _FakeConn(family=[root, mid, leaf])
    repeat = r.PreviewIn(template_id=uuid.uuid4(), source="repeat", repeat_of=mid)
    assert await svc.ignore_for(conn, repeat) == [root, mid, leaf]
    assert [p for s, p in conn.calls if s is svc.REPEAT_FAMILY_SQL] == [{"src": mid}]
    for source in ("paste", "upload", "wa_contacts"):
        assert await svc.ignore_for(conn, r.PreviewIn(template_id=uuid.uuid4(), source=source, repeat_of=mid)) == []
    assert await svc.ignore_for(conn, r.PreviewIn(template_id=uuid.uuid4(), source="repeat")) == []


async def test_a_draft_cannot_be_built_on_an_inactive_template():
    conn = _FakeConn(template=_template(active=False))
    req = r.CreateIn(template_id=uuid.uuid4(), source="paste", name="x", paste="9876543210, Asha")
    with pytest.raises(ValueError, match="inactive"):
        await svc.create_draft(conn, req, ADMIN)
    assert _inserts(conn, "wa_campaigns") == [], "nothing is written for a refused draft"


@pytest.mark.parametrize("paste", ["", "not a phone\nalso not\n", "9876543210"])  # empty · all invalid · missing slot 1
async def test_a_list_with_nothing_sendable_saves_no_draft(paste):
    tid = uuid.uuid4()
    conn = _FakeConn(template=_template(id=tid))
    with pytest.raises(ValueError) as e:
        await svc.create_draft(conn, r.CreateIn(template_id=tid, source="paste", name="x", paste=paste), ADMIN)
    assert str(e.value) == NOTHING
    assert _inserts(conn, "wa_campaigns") == [] and _inserts(conn, "wa_campaign_recipients") == []


@pytest.mark.parametrize("reason", ["opted_out", "rejected", "is_lead", "no_whatsapp", "cooldown"])
async def test_an_all_skipped_list_saves_no_draft(reason):
    """Skip verdicts are frozen at build time: a draft whose every row was skipped has 0 queued and can never send."""
    tid = uuid.uuid4()
    conn = _FakeConn(template=_template(id=tid), excluded={"9876543210": reason, "9876543211": reason})
    req = r.CreateIn(template_id=tid, source="paste", name="x", var_cols=[1], paste="9876543210, Asha\n9876543211, Ravi")
    with pytest.raises(ValueError) as e:
        await svc.create_draft(conn, req, ADMIN)
    assert str(e.value) == NOTHING
    assert _inserts(conn, "wa_campaigns") == [] and _inserts(conn, "wa_campaign_recipients") == []


async def test_a_list_of_only_skipped_invalid_and_duplicate_rows_saves_no_draft():
    tid = uuid.uuid4()
    conn = _FakeConn(template=_template(id=tid), excluded={"9876543210": "opted_out"})
    req = r.CreateIn(template_id=tid, source="paste", name="x", var_cols=[1],
                     paste="9876543210, Asha\nnot a phone\n9876543210, Asha again")   # skipped · invalid · duplicate
    with pytest.raises(ValueError) as e:
        await svc.create_draft(conn, req, ADMIN)
    assert str(e.value) == NOTHING and _inserts(conn, "wa_campaigns") == []


@pytest.mark.parametrize("paste", ["9876543210, Asha\n9876543211, Ravi", "9876543211, Ravi\n9876543210, Asha"])  # either order
async def test_one_valid_and_one_skipped_row_is_still_saved(paste):
    """The skipped row is kept (with its reason) beside the one that will send."""
    tid = uuid.uuid4()
    conn = _FakeConn(template=_template(id=tid), excluded={"9876543211": "opted_out"})
    await svc.create_draft(conn, r.CreateIn(template_id=tid, source="paste", name="x", var_cols=[1], paste=paste), ADMIN)
    [(_, rows)] = _inserts(conn, "wa_campaign_recipients")
    assert sorted((x["phone10"], x["status"], x["skip_reason"]) for x in rows) == [
        ("9876543210", "queued", None), ("9876543211", "skipped", "opted_out")]


# ── the two endpoints ─────────────────────────────────────────────────────────────

def test_preview_and_create_are_posts_on_the_router():
    routes = {(m, route.path) for route in r.router.routes for m in getattr(route, "methods", ())}
    assert ("POST", "/wa-campaigns/preview") in routes and ("POST", "/wa-campaigns") in routes


async def test_preview_reports_counts_samples_and_the_daily_limit(monkeypatch):
    monkeypatch.setattr(get_settings(), "WA_DAILY_SEND_LIMIT", 2)
    eng = _use(monkeypatch, _FakeConn(template=_template(), excluded={"9876543213": "opted_out"}))
    paste = "\n".join(f"987654321{i}, N{i}" for i in range(5)) + "\nbad\n9876543210, again"
    out = await r.preview(r.PreviewIn(template_id=uuid.uuid4(), source="paste", name_col=1, var_cols=[1], paste=paste))
    assert out["counts"] == {"valid": 4, "invalid": 1, "duplicate": 1, "skipped": 1}
    assert out["samples"][0] == "Hi N0, a flat in Noida for you" and len(out["samples"]) == 4
    assert out["over_daily_limit"] is True and out["daily_limit"] == 2 and out["headers"] == []
    assert not _inserts(eng.conn, "wa_campaigns"), "a preview writes nothing"


async def test_preview_counts_every_row_but_returns_the_first_200(monkeypatch):
    monkeypatch.setattr(get_settings(), "WA_DAILY_SEND_LIMIT", 205)   # exactly the number of valid rows
    _use(monkeypatch, _FakeConn(template=_template()))
    paste = "\n".join(f"98765{i:05d}, N{i}" for i in range(205))
    out = await r.preview(r.PreviewIn(template_id=uuid.uuid4(), source="paste", var_cols=[1], paste=paste))
    assert out["counts"]["valid"] == 205 and len(out["rows"]) == 200 and len(out["samples"]) == 5
    assert out["over_daily_limit"] is False
    monkeypatch.setattr(get_settings(), "WA_DAILY_SEND_LIMIT", 204)   # one over → warn (exactly at the limit is fine)
    again = await r.preview(r.PreviewIn(template_id=uuid.uuid4(), source="paste", var_cols=[1], paste=paste))
    assert again["over_daily_limit"] is True


async def test_preview_maps_refusals_to_http_errors(monkeypatch):
    _use(monkeypatch, _FakeConn(template=None))
    with pytest.raises(HTTPException) as e:
        await r.preview(r.PreviewIn(template_id=uuid.uuid4(), source="paste", paste="9876543210"))
    assert e.value.status_code == 404

    _use(monkeypatch, _FakeConn(template=_template()))
    with pytest.raises(HTTPException) as e:
        await r.preview(r.PreviewIn(template_id=uuid.uuid4(), source="upload", file_name="x.xlsx",
                                    file_b64=base64.b64encode(b"not a zip").decode()))
    assert e.value.status_code == 422 and "couldn't read that file" in e.value.detail

    with pytest.raises(HTTPException) as e:
        await r.preview(r.PreviewIn(template_id=uuid.uuid4(), source="repeat"))
    assert (e.value.status_code, e.value.detail) == (422, "pick the campaign whose list to repeat")


async def test_a_repeat_ignores_the_whole_repeat_tree_in_both_preview_and_create(monkeypatch):
    """Chain A → B (repeat of A) → C (repeat of B): repeating B must forgive A's sends too, in the preview the
    admin reads AND in the draft that is saved — they have to agree."""
    root, mid, leaf, tid = (uuid.uuid4() for _ in range(4))
    old = [{"phone10": "9876543210", "name": "Asha", "variables": ["Asha", "Noida"]}]
    eng = _use(monkeypatch, _FakeConn(template=_template(id=tid), repeat=old, family=[root, mid, leaf]))
    await r.preview(r.PreviewIn(template_id=tid, source="repeat", repeat_of=mid))
    assert [x["ignore_campaigns"] for x in _lookups(eng.conn)] == [[root, mid, leaf]], "the preview's own exclusions"
    await r.create_campaign(r.CreateIn(template_id=tid, source="repeat", repeat_of=mid, name="again"), ADMIN)
    assert [x["ignore_campaigns"] for x in _lookups(eng.conn)] == [[root, mid, leaf]] * 2, "and the saved draft's"
    assert [p for s, p in eng.conn.calls if s is svc.REPEAT_FAMILY_SQL] == [{"src": mid}] * 2


async def test_a_preview_of_a_fresh_list_ignores_nothing(monkeypatch):
    eng = _use(monkeypatch, _FakeConn(template=_template(), family=[uuid.uuid4()]))
    await r.preview(r.PreviewIn(template_id=uuid.uuid4(), source="paste", repeat_of=uuid.uuid4(), var_cols=[0],
                                paste="9876543210"))
    assert [x["ignore_campaigns"] for x in _lookups(eng.conn)] == [[]]


async def test_create_answers_with_the_new_id_and_maps_refusals(monkeypatch):
    tid = uuid.uuid4()
    eng = _use(monkeypatch, _FakeConn(template=_template(id=tid)))
    out = await r.create_campaign(r.CreateIn(template_id=tid, source="paste", name="Diwali", var_cols=[1],
                                             paste="9876543210, Asha"), ADMIN)
    assert uuid.UUID(out["id"]) and len(_inserts(eng.conn, "wa_campaigns")) == 1

    _use(monkeypatch, _FakeConn(template=_template(active=False)))
    with pytest.raises(HTTPException) as e:
        await r.create_campaign(r.CreateIn(template_id=tid, source="paste", name="x", paste="9876543210"), ADMIN)
    assert (e.value.status_code, e.value.detail) == (422, "that template is inactive")

    _use(monkeypatch, _FakeConn(template=None))
    with pytest.raises(HTTPException) as e:
        await r.create_campaign(r.CreateIn(template_id=tid, source="paste", name="x", paste="9876543210"), ADMIN)
    assert e.value.status_code == 404

    _use(monkeypatch, _FakeConn(template=_template()))
    with pytest.raises(HTTPException) as e:
        await r.create_campaign(r.CreateIn(template_id=tid, source="repeat", name="x"), ADMIN)
    assert e.value.status_code == 422, "no empty draft for a repeat that names no campaign"


async def test_a_campaign_to_repeat_that_does_not_exist_is_a_404_not_an_fk_500(monkeypatch):
    eng = _use(monkeypatch, _FakeConn(template=_template(), source_slots=None))
    with pytest.raises(HTTPException) as e:
        await r.preview(r.PreviewIn(template_id=uuid.uuid4(), source="repeat", repeat_of=uuid.uuid4()))
    assert e.value.status_code == 404 and "campaign to repeat" in e.value.detail
    with pytest.raises(HTTPException) as e:
        await r.create_campaign(r.CreateIn(template_id=uuid.uuid4(), source="repeat", repeat_of=uuid.uuid4(),
                                           name="x"), ADMIN)
    assert e.value.status_code == 404
    assert _inserts(eng.conn, "wa_campaigns") == [], "nothing reached the FK"
    assert eng.log[-1] == ("begin", "rollback")


async def test_a_repeat_with_a_different_slot_count_is_a_422_at_the_endpoints(monkeypatch):
    _use(monkeypatch, _FakeConn(template=_template(), source_slots=1))
    want = "That list was sent with a template that has 1 variable — pick a template with 1, or upload the list again"
    with pytest.raises(HTTPException) as e:
        await r.preview(r.PreviewIn(template_id=uuid.uuid4(), source="repeat", repeat_of=uuid.uuid4()))
    assert (e.value.status_code, e.value.detail) == (422, want)
    with pytest.raises(HTTPException) as e:
        await r.create_campaign(r.CreateIn(template_id=uuid.uuid4(), source="repeat", repeat_of=uuid.uuid4(),
                                           name="x"), ADMIN)
    assert (e.value.status_code, e.value.detail) == (422, want)


@pytest.mark.parametrize("paste, excluded", [("not a phone", {}),                                  # all invalid
                                             ("9876543210, Asha", {"9876543210": "cooldown"})])    # all skipped
async def test_a_list_with_nothing_sendable_is_a_422_and_rolls_back(monkeypatch, paste, excluded):
    tid = uuid.uuid4()
    eng = _use(monkeypatch, _FakeConn(template=_template(id=tid), excluded=excluded))
    with pytest.raises(HTTPException) as e:
        await r.create_campaign(r.CreateIn(template_id=tid, source="paste", name="x", var_cols=[1], paste=paste), ADMIN)
    assert (e.value.status_code, e.value.detail) == (422, NOTHING)
    assert eng.log == [("begin", "rollback")] and _inserts(eng.conn, "wa_campaigns") == []


async def test_create_writes_through_begin_which_commits_and_preview_only_connects(monkeypatch):
    """Through connect() nothing would ever commit: the draft would 200 and vanish."""
    tid = uuid.uuid4()
    eng = _use(monkeypatch, _FakeConn(template=_template(id=tid)))
    await r.create_campaign(r.CreateIn(template_id=tid, source="paste", name="x", var_cols=[1],
                                       paste="9876543210, Asha"), ADMIN)
    assert eng.log == [("begin", "commit")]
    eng.log.clear()
    await r.preview(r.PreviewIn(template_id=tid, source="paste", paste="9876543210, Asha"))
    assert eng.log == [("connect", "close")]
    assert len(_inserts(eng.conn, "wa_campaigns")) == 1, "the preview inserted nothing of its own"


async def test_only_not_found_becomes_a_404_a_real_bug_stays_a_500(monkeypatch):
    """IndexError / KeyError are LookupErrors: catching LookupError turned any slip in the service into 'not found'."""
    _use(monkeypatch, _FakeConn(template=_template()))
    for exc in (IndexError("list index out of range"), KeyError("variable_count")):
        async def boom(conn, req, exc=exc):
            raise exc
        monkeypatch.setattr(svc, "candidates_for", boom)
        with pytest.raises(type(exc)):
            await r.preview(r.PreviewIn(template_id=uuid.uuid4(), source="paste"))
        with pytest.raises(type(exc)):
            await r.create_campaign(r.CreateIn(template_id=uuid.uuid4(), source="paste", name="x"), ADMIN)


# ── Task 6: the campaigns list and its funnel ─────────────────────────────────────

FUNNEL_KEYS = {"recipients", "queued", "accepted", "sent", "delivered", "read", "failed", "skipped", "unknown", "replied",
               "no_reply"}
API_TS = Path(__file__).parents[2] / "frontend" / "src" / "lib" / "api.ts"


def test_funnel_counts_come_from_recipients_not_stored_columns():
    sql = svc.FUNNEL_SQL.text
    assert "FROM wa_campaign_recipients" in sql and "count(*) FILTER" in sql
    # a Gupshup 2xx is "accepted", not sent — its own box until the sent receipt lands (contract §0 rule 3)
    assert "FILTER (WHERE r.status = 'accepted')" in sql
    # a reply is credited by the ONE attribution rule the recipient table uses
    assert svc.REPLY_CREDIT in sql and svc.NEXT_SEND_JOIN in sql


def test_the_funnel_sql_selects_exactly_the_columns_the_endpoint_reads():
    """The endpoint reads f[k] for every key of ZERO_FUNNEL, and no test runs the SQL: an alias the SQL doesn't
    select would be a KeyError on the first campaign that has recipients — in production only."""
    sql = svc.FUNNEL_SQL.text
    outer = sql.split("FROM wa_campaign_recipients r\n", 1)[0]   # the select list, not the laterals' own aliases
    assert sorted(re.findall(r"\bAS\s+(\w+)", outer)) == sorted(r.ZERO_FUNNEL) == sorted(FUNNEL_KEYS)
    assert "SELECT r.campaign_id," in sql and "GROUP BY r.campaign_id" in sql and "r.campaign_id = ANY(:ids)" in sql


def test_each_funnel_box_counts_the_statuses_it_claims():
    """sent ⊇ delivered ⊇ read (a read message WAS delivered and sent); accepted is only the rows still waiting for
    their sent receipt, or the box would double-count everything that moved on."""
    sql = " ".join(svc.FUNNEL_SQL.text.split())   # the SQL is column-aligned: pin the predicates, not the padding
    assert "FILTER (WHERE r.status IN ('sent','delivered','read')) AS sent" in sql
    assert "FILTER (WHERE r.status IN ('delivered','read')) AS delivered" in sql
    assert "FILTER (WHERE r.status = 'read') AS read" in sql
    assert "FILTER (WHERE r.status = 'submitted') AS unknown" in sql, "stuck in `submitted` = outcome unknown"


def test_the_campaign_list_is_a_get_on_the_router():
    routes = {(m, route.path) for route in r.router.routes for m in getattr(route, "methods", ())}
    assert ("GET", "/wa-campaigns") in routes


class _ListConn:
    """The list endpoint's two reads: the campaigns (an inline statement), then FUNNEL_SQL for their ids."""

    def __init__(self, campaigns, funnel=()):
        self.campaigns, self.funnel, self.calls = list(campaigns), list(funnel), []

    async def execute(self, stmt, params=None):
        self.calls.append((stmt, params))
        return _Result(self.funnel if stmt is svc.FUNNEL_SQL else self.campaigns)


def _campaign(**over):
    return {"id": uuid.uuid4(), "name": "Diwali", "source": "paste", "status": "draft",
            "created_at": datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc), "launched_at": None, "finished_at": None,
            "auto_campaign_id": None, "repeat_of": None, "template_name": "site_visit_followup", **over}


def _funnel_row(campaign_id, **over):
    return {"campaign_id": campaign_id, **dict.fromkeys(FUNNEL_KEYS, 0), **over}


async def test_the_list_returns_each_campaign_with_its_counts(monkeypatch):
    a, b, c, src, auto = (uuid.uuid4() for _ in range(5))
    conn = _ListConn(
        [_campaign(id=a, name="Auto · 2 Oct", source="auto", status="done", auto_campaign_id=auto, repeat_of=src,
                   launched_at=datetime(2026, 10, 2, 5, 30, tzinfo=timezone.utc),
                   finished_at=datetime(2026, 10, 2, 5, 40, tzinfo=timezone.utc)),
         _campaign(id=b), _campaign(id=c)],
        [_funnel_row(a, recipients=10, sent=8, delivered=6, read=3, replied=1, failed=1, skipped=1)])
    eng = _use(monkeypatch, conn)
    out = await r.list_campaigns()
    first, second, third = out["items"]
    assert first == {
        "id": str(a), "name": "Auto · 2 Oct", "template_name": "site_visit_followup", "source": "auto",
        "status": "done", "created_at": "2026-10-01T09:30:00+00:00", "launched_at": "2026-10-02T05:30:00+00:00",
        "finished_at": "2026-10-02T05:40:00+00:00", "auto_campaign_id": str(auto), "repeat_of": str(src),
        "counts": {**dict.fromkeys(FUNNEL_KEYS, 0), "recipients": 10, "sent": 8, "delivered": 6, "read": 3,
                   "replied": 1, "failed": 1, "skipped": 1}}
    # a campaign with no recipients has no funnel row: zeros (the UI reads every box), never a missing key,
    # and each gets its OWN dict — a shared one would carry one campaign's edit into the next
    assert second["counts"] == dict.fromkeys(FUNNEL_KEYS, 0) and second["counts"] is not third["counts"]
    assert second["counts"] is not r.ZERO_FUNNEL
    assert (second["launched_at"], second["finished_at"], second["auto_campaign_id"], second["repeat_of"]) == (None,) * 4
    assert [i["id"] for i in out["items"]] == [str(a), str(b), str(c)], "the SQL's order is kept"
    assert eng.log == [("connect", "close")], "a read: connect(), never begin()"


async def test_the_counts_are_plain_ints(monkeypatch):
    """Postgres count(*) is a bigint; asyncpg hands back int, but a Decimal/str from another driver must not reach
    the UI as a string that sorts and sums wrongly."""
    a = uuid.uuid4()
    _use(monkeypatch, _ListConn([_campaign(id=a)], [_funnel_row(a, recipients="12", sent=3.0)]))
    [item] = (await r.list_campaigns())["items"]
    assert item["counts"]["recipients"] == 12 and type(item["counts"]["recipients"]) is int
    assert type(item["counts"]["sent"]) is int


async def test_the_funnel_is_asked_for_the_listed_ids_as_uuid_objects(monkeypatch):
    a, b = uuid.uuid4(), uuid.uuid4()
    conn = _ListConn([_campaign(id=a), _campaign(id=b)])
    _use(monkeypatch, conn)
    await r.list_campaigns()
    [(_, params)] = [c for c in conn.calls if c[0] is svc.FUNNEL_SQL]
    assert params == {"ids": [a, b]} and all(isinstance(i, uuid.UUID) for i in params["ids"])


async def test_no_campaigns_means_no_funnel_query(monkeypatch):
    conn = _ListConn([])
    _use(monkeypatch, conn)
    assert await r.list_campaigns() == {"items": []}
    assert all(s is not svc.FUNNEL_SQL for s, _ in conn.calls), "ANY(empty list) is still a round trip to Neon"


async def test_the_campaign_list_is_newest_first_and_capped(monkeypatch):
    conn = _ListConn([_campaign()])
    _use(monkeypatch, conn)
    await r.list_campaigns()
    sql = str(conn.calls[0][0])
    assert re.search(r"ORDER BY c\.created_at DESC\s+LIMIT 200\b", sql), "newest 200, recomputed on every poll"
    assert "FROM wa_campaigns c JOIN wa_templates t ON t.id = c.template_id" in sql


# What the UI is typed against. Each pair below is the same contract written twice — once as the pydantic model /
# SQL that serves it, once as the TypeScript the Campaigns tab compiles against — so renaming a field on one side
# fails here instead of showing up as a blank column, or as a 422 nobody can explain, in production.

def _ts_keys(interface: str) -> set[str]:
    """The keys of `export interface <name> { … }` in api.ts (nested shapes are named interfaces of their own,
    so every key sits at the top of its own line)."""
    m = re.search(rf"export interface {interface}(?: extends \w+)? \{{\n(.*?)\n\}}", API_TS.read_text(encoding="utf-8"), re.S)
    assert m, f"api.ts has no `export interface {interface}`"
    return set(re.findall(r"^\s+(\w+)\??:", m.group(1), re.M))


def test_the_preview_and_create_bodies_the_ui_sends_are_the_ones_the_server_reads():
    assert _ts_keys("WaPreviewIn") == set(r.PreviewIn.model_fields)
    assert _ts_keys("WaPreviewIn") | _ts_keys("WaCreateIn") == set(r.CreateIn.model_fields)


def test_the_funnel_the_ui_types_is_the_funnel_the_api_sends():
    assert _ts_keys("WaFunnel") == FUNNEL_KEYS


async def test_the_campaign_row_the_ui_types_is_what_the_list_sends(monkeypatch):
    _use(monkeypatch, _ListConn([_campaign()]))
    [item] = (await r.list_campaigns())["items"]
    assert _ts_keys("WaCampaignRow") == set(item)


def test_the_preview_the_ui_types_is_what_preview_sends():
    sent = {"headers", "counts", "rows", "samples", "over_daily_limit", "daily_limit"}   # routers/wa_campaigns.preview
    assert _ts_keys("WaPreview") == sent
    assert _ts_keys("WaPreviewCounts") == set(svc.counts([]))
    assert _ts_keys("WaPreviewRow") == {"phone10", "name", "variables", "status", "reason"}   # svc.classify's rows


def test_every_reason_the_server_gives_a_row_has_a_label_in_the_ui():
    """EXCLUDE_SQL's five skip reasons + build()'s three (Candidate.error). A reason with no label would show the
    admin a raw snake_case word; a label with no reason is dead text."""
    server = set(re.findall(r"THEN '(\w+)'", svc.EXCLUDE_SQL.text)) | {"invalid_phone", "missing_variable", "duplicate"}
    block = re.search(r"export const WA_REASON_LABEL[^=]*= \{\n(.*?)\n\};", API_TS.read_text(encoding="utf-8"), re.S)
    assert block, "api.ts has no WA_REASON_LABEL"
    assert set(re.findall(r"^\s+(\w+):", block.group(1), re.M)) == server


def test_the_sources_the_ui_offers_are_the_ones_the_server_accepts():
    import typing
    server = set(typing.get_args(r.PreviewIn.model_fields["source"].annotation))
    m = re.search(r"export type WaSource =([^;]*);", API_TS.read_text(encoding="utf-8"))
    assert m and set(re.findall(r'"(\w+)"', m.group(1))) == server


# ── Task 7: the send loop's rules ────────────────────────────────────────────────

def test_an_opt_out_after_the_list_was_built_still_stops_the_send():
    """Skips are frozen at build time; opt-outs must be re-checked at send time (Meta: honour opt-outs)."""
    sql = svc.SKIP_OPTED_OUT_SQL.text
    assert "SET status = 'skipped', skip_reason = c.tag" in sql
    assert "r.status = 'queued'" in sql and "c.tag IN ('opted_out', 'rejected')" in sql
    import inspect
    src = inspect.getsource(svc._send_one)
    assert src.index("SKIP_OPTED_OUT_SQL") < src.index("CLAIM_SQL"), "re-check before claiming"


def test_claim_is_idempotent_and_only_while_the_campaign_is_sending():
    """G-9: a pause / cancel / auto-pause must stop the batch the loop already fetched."""
    sql = " ".join(svc.CLAIM_SQL.text.split())
    assert "SET status = 'submitted'" in sql and "WHERE r.id = :id AND r.status = 'queued'" in sql
    assert "FROM wa_campaigns c" in sql and "AND c.id = r.campaign_id AND c.status = 'sending'" in sql
    assert "RETURNING r.id, r.phone10, r.variables" in sql


def test_the_loop_only_sends_campaigns_that_are_sending_and_in_window():
    sql = svc.DUE_SQL.text
    assert "c.status = 'sending'" in sql
    assert "Asia/Kolkata" in sql and "send_window_start" in sql and "send_window_end" in sql


def test_the_loop_sends_in_list_order():
    assert "ORDER BY position, id" in svc.NEXT_QUEUED_SQL.text


def test_a_gupshup_2xx_makes_the_row_accepted_not_sent():
    """A 2xx means Gupshup took it; 'sent' only comes from the sent receipt (contract §0 rule 3)."""
    sql = svc.ACCEPTED_SQL.text
    assert "status = 'accepted'" in sql and "gupshup_id = :g" in sql and "sent_at = now()" in sql
    assert "AND status = 'submitted'" in sql


def test_a_refused_send_goes_back_to_the_queue():
    sql = svc.REQUEUE_SQL.text
    assert "status = 'queued'" in sql and "AND status = 'submitted'" in sql
    assert svc.BACKOFF_SECONDS == 60


def test_the_daily_cap_is_a_moving_24h_not_the_calendar_day():
    """Meta counts unique people over a moving 24 h (contract Delta 16)."""
    sql = svc.SENT_24H_SQL.text
    assert "count(DISTINCT phone10)" in sql and "interval '24 hours'" in sql
    assert "::date" not in sql


def test_the_default_limit_is_metas_lowest_tier():
    from app.config import Settings
    assert Settings.model_fields["WA_DAILY_SEND_LIMIT"].default == 250


def test_unconfigured_leaves_rows_queued(monkeypatch):
    """Review Focus #5 (loop half): tick() must return before picking any rows."""
    import inspect
    src = inspect.getsource(svc.tick)
    assert src.index("gupshup_template_configured") < src.index("NEXT_QUEUED_SQL")


def test_recipient_statuses_only_move_forward():
    r = svc.STATUS_RANK
    assert r["read"] > r["delivered"] > r["sent"] > r["accepted"] > r["submitted"] > r["queued"]
    assert svc.EVENT_RANK["enqueued"] == 0, "enqueued only teaches ids; 'accepted' already means Gupshup took it"
    sql = svc.RECEIPT_SQL.text
    assert "gupshup_id = :key OR whatsapp_id = CAST(:wa_id AS text)" in sql
    assert ":rank > (CASE status" in sql and "'accepted'" in sql
    assert "COALESCE(whatsapp_id, CAST(:learn AS text))" in sql
    assert "RETURNING campaign_id, phone10" in sql


def test_a_campaign_level_failure_pauses_only_a_sending_campaign():
    sql = svc.PAUSE_SQL.text
    assert "status = 'paused'" in sql and "status_note" in sql and "AND status = 'sending'" in sql


def test_the_funnel_and_the_recipient_table_share_one_attribution_rule():
    """D-C2 / G-1: the boxes and the table filters must never disagree about who replied."""
    for sql in (svc.FUNNEL_SQL.text, svc.RECIPIENTS_SQL.text):
        assert svc.REPLY_CREDIT in sql and svc.NEXT_SEND_JOIN in sql
        assert sql.count("FROM wa_messages m") == 1, "exactly one place reads replies"


def test_a_reply_belongs_to_the_most_recent_send_that_actually_went_out():
    """D-C2(a): A delivered, then B accepted and FAILED (131049 keeps sent_at) → the reply is A's, not B's.
    The window ends at the next send that WENT OUT; a failed send neither ends it nor earns a reply."""
    assert svc.WENT_OUT == "('accepted','sent','delivered','read')"
    nxt = " ".join(svc.NEXT_SEND_JOIN.split())
    assert "SELECT min(r2.sent_at) AS at FROM wa_campaign_recipients r2" in nxt
    # D-M9: one bounded lookup per recipient, skipped outright for rows that can't be credited anyway
    assert "WHERE r.status IN ('accepted','sent','delivered','read') -- only those rows" in nxt
    assert "r2.phone10 = r.phone10 AND r2.sent_at > r.sent_at AND r2.status IN ('accepted','sent','delivered','read')" in nxt
    credit = " ".join(svc.REPLY_CREDIT.split())
    assert credit.startswith("right(m.phone, 10) = r.phone10 AND m.direction = 'in' "
                             "AND r.status IN ('accepted','sent','delivered','read')")
    assert "m.created_at > r.sent_at AND (nxt.at IS NULL OR m.created_at <= nxt.at)" in credit


def test_a_reply_that_names_its_send_is_credited_to_that_send_only():
    """D-C2(b) / D-M8: a tap whose context names run 1, made after run 2 went out, is run 1's — button AND reply on
    the same row — and never run 2's too. context.id is compared to BOTH ids (Doc A taps carry only context.id)."""
    credit = " ".join(svc.REPLY_CREDIT.split())
    names_r = ("(m.raw->'payload'->'context'->>'gsId' = r.gupshup_id"
               " OR m.raw->'payload'->'context'->>'id' IN (r.gupshup_id, r.whatsapp_id))")
    names_rx = names_r.replace("r.", "rx.").replace("(rx.gupshup", "(rx.gupshup")
    assert f"AND ({names_r} OR (r.sent_at IS NOT NULL" in credit, "exact match first, whenever it was sent"
    assert ("(m.raw->'payload'->'context' IS NULL OR NOT EXISTS (SELECT 1 FROM wa_campaign_recipients rx "
            f"WHERE rx.phone10 = r.phone10 AND {names_rx}))") in credit, "the time rule only for a context naming no send"


def test_the_button_is_the_first_tap_among_the_replies_credited_to_that_row():
    sql = " ".join(svc.RECIPIENTS_SQL.text.split())
    assert "(array_agg(m.body ORDER BY m.created_at) FILTER (WHERE m.msg_type = 'quick_reply'))[1] AS button" in sql
    assert "rep.button" in sql and "btn" not in sql, "one lateral, not a second attribution rule for buttons"


def test_no_reply_counts_rows_that_went_out_with_nothing_credited():
    sql = svc.RECIPIENTS_SQL.text
    assert "r.status IN ('accepted','sent','delivered','read') AND COALESCE(rep.replies, 0) = 0" in sql
    funnel = " ".join(svc.FUNNEL_SQL.text.split())
    assert "count(*) FILTER (WHERE rep.hit) AS replied" in funnel
    assert "count(*) FILTER (WHERE r.status IN ('accepted','sent','delivered','read') AND NOT rep.hit) AS no_reply" in funnel


def test_retry_refuses_what_meta_says_never_to_retry():
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    assert svc.retry_refusal("131050: opted out", now) is not None
    assert svc.retry_refusal("1002: Number Does Not Exist On WhatsApp", now) is not None
    assert svc.retry_refusal("131049: per-user marketing limit", now - timedelta(hours=2)) is not None
    assert svc.retry_refusal("131049: per-user marketing limit", now - timedelta(hours=25)) is None
    assert svc.retry_refusal("131026: Message undeliverable", now) is None  # allowed by hand (user may update WhatsApp)
    assert svc.retry_refusal(None, now) is None


def test_the_retry_endpoint_consults_retry_refusal_before_requeueing():
    import inspect
    src = inspect.getsource(r.retry_recipient)
    assert src.index("retry_refusal") < src.index("RETRY_SQL")
    assert "409" in src


def test_literal_campaign_routes_are_declared_above_the_cid_routes():
    """A literal /wa-campaigns/<word> GET declared after /wa-campaigns/{cid} would be read as a campaign id."""
    gets = [(i, rt.path) for i, rt in enumerate(r.router.routes) if "GET" in rt.methods]
    cid_at = min(i for i, p in gets if p.startswith("/wa-campaigns/{cid}"))
    literals = [(i, p) for i, p in gets if p.startswith("/wa-campaigns/") and "{" not in p]
    assert literals, "expected at least /wa-campaigns/templates"
    assert all(i < cid_at for i, p in literals), literals


def test_the_recipients_endpoint_uses_the_items_envelope_and_validates_the_filter():
    import inspect
    src = inspect.getsource(r.campaign_recipients) + inspect.getsource(r._recipient_rows)
    assert '{"items"' in src and "422" in src
    for f in ("all", "accepted", "sent", "delivered", "read", "replied", "no_reply", "failed", "skipped", "submitted"):
        assert f in r.RECIPIENT_FILTERS


def test_the_export_defuses_spreadsheet_formulas():
    for lead in ("=", "+", "-", "@", "\t", "\r"):
        assert r._csv_cell(lead + "SUM(A1)") == "'" + lead + "SUM(A1)", repr(lead)
    assert r._csv_cell("=HYPERLINK(\"x\")").startswith("'=")
    assert r._csv_cell("+91 98") == "'+91 98" and r._csv_cell(None) == "" and r._csv_cell("hello") == "hello"


def test_the_export_filename_survives_a_hindi_campaign_name():
    """D-M5: headers are latin-1 — a Hindi name in filename= was a 500. ASCII fallback + RFC 6266 filename*."""
    h = r._attachment("दिवाली offer / Noida")
    h.encode("latin-1")   # would raise on the old header
    assert h == ("attachment; filename=\"______ offer _ Noida.csv\"; "
                 "filename*=UTF-8''%E0%A4%A6%E0%A4%BF%E0%A4%B5%E0%A4%BE%E0%A4%B2%E0%A5%80%20offer%20_%20Noida.csv")


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _Conn:
    def __init__(self, answers):
        self._answers = list(answers)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *_a, **_k):
        return _Res(self._answers.pop(0))


class _Eng:
    def __init__(self, answers):
        self._answers = answers

    def connect(self):
        return _Conn(self._answers)


async def test_export_and_detail_shape_with_a_fake_connection(monkeypatch):
    now = datetime.now(timezone.utc)
    rec = {"id": uuid.uuid4(), "phone10": "9876543210", "name": "=Ravi", "variables": [], "status": "read",
           "skip_reason": None, "error": None, "owner": "Asha", "sent_at": now, "status_at": now,
           "first_reply": "Yes", "replied_at": now, "replies": 1, "button": "Yes"}
    camp = {"id": uuid.uuid4(), "name": "Diwali / push", "source": "upload", "status": "paused",
            "status_note": "Paused by Gupshup error 132015: x", "created_at": now, "launched_at": now,
            "finished_at": None, "auto_campaign_id": None, "repeat_of": None, "send_window_start": "10:00",
            "send_window_end": "19:00", "rate_per_minute": 30, "template_name": "t", "template_body": "Hi",
            "template_buttons": ["Yes"]}
    monkeypatch.setattr(r, "_engine", lambda: _Eng([[camp], [rec]]))
    resp = await r.campaign_export(camp["id"])
    assert resp.headers["content-disposition"] == (
        'attachment; filename="Diwali _ push.csv"; filename*=UTF-8\'\'Diwali%20_%20push.csv')
    body = "".join([c async for c in resp.body_iterator])
    assert body.startswith("\ufeffname,phone,status"), "a UTF-8 BOM, or Excel garbles Hindi names (D-M5)"
    assert "'=Ravi" in body

    funnel = {k: 0 for k in r.ZERO_FUNNEL} | {"recipients": 1, "read": 1}
    monkeypatch.setattr(r, "_engine", lambda: _Eng([[camp], [funnel], [rec, rec]]))
    d = await r.campaign_detail(camp["id"])
    assert d["buttons"] == {"Yes": 2} and d["counts"]["read"] == 1
    assert d["campaign"]["status_note"].startswith("Paused") and d["campaign"]["template_buttons"] == ["Yes"]

    monkeypatch.setattr(r, "_engine", lambda: _Eng([[]]))
    with pytest.raises(HTTPException) as e:
        await r.campaign_detail(uuid.uuid4())
    assert e.value.status_code == 404
