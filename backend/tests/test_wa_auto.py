import inspect
from datetime import date

import pytest
from pydantic import ValidationError

from app.routers import wa_campaigns as r
from app.services import wa_campaigns as svc


def test_missed_slots_collapse_to_one_run():
    # cron down 3 days on a daily schedule: run once for today, next slot is tomorrow
    assert svc.next_slot_after(date(2026, 10, 1), 1, today=date(2026, 10, 4)) == date(2026, 10, 5)
    # weekly, on time
    assert svc.next_slot_after(date(2026, 10, 1), 7, today=date(2026, 10, 1)) == date(2026, 10, 8)


def test_one_run_per_slot_is_enforced_by_the_database():
    sql = svc.INSERT_RUN_SQL.text
    assert "ON CONFLICT ON CONSTRAINT uq_wa_campaign_auto_slot DO NOTHING" in sql
    assert "RETURNING id" in sql


def test_only_active_definitions_with_a_due_slot_and_active_template_run():
    sql = svc.DUE_AUTO_SQL.text
    assert "a.active" in sql and "t.active" in sql
    assert "Asia/Kolkata" in sql and "a.next_slot" in sql and "a.run_at" in sql


def test_auto_cooldown_ignores_the_whole_family():
    """A daily auto with a 7-day cooldown must not empty itself on run 3 because run 1
    reached everyone 2 days ago: the seed and all its own runs are ignored (spec §4.4)."""
    src = inspect.getsource(svc.auto_list)
    assert "seed_campaign_id" in src and "REPEAT_FAMILY_SQL" in src and "ignore_campaigns=family" in src
    assert "auto_list(" in inspect.getsource(svc._run_one)


def test_the_dry_run_uses_the_same_list_builder_and_writes_nothing():
    src = inspect.getsource(svc.auto_dry_run)
    assert "auto_list(" in src
    assert not any(w in src.upper() for w in ("INSERT", "UPDATE ", "DELETE", "COMMIT"))
    assert "SELECT" in svc.SEED_LAST_RUN_SQL.text and "UPDATE" not in svc.SEED_LAST_RUN_SQL.text


def test_run_now_ignores_the_clock_but_still_needs_an_active_definition():
    assert "a.id = :id" in svc.ONE_AUTO_SQL.text and "a.active" in svc.ONE_AUTO_SQL.text
    assert "next_slot" not in svc.ONE_AUTO_SQL.text.split("WHERE")[1]


def test_cron_task_is_registered():
    import importlib.util
    import pathlib
    p = pathlib.Path(__file__).parents[1] / "scripts" / "20_cron_tasks.py"
    spec = importlib.util.spec_from_file_location("cron", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert "wa_auto" in m.TASKS and "wa_auto" in m.RUNNERS


# ── the admin API ────────────────────────────────────────────────────────────────
import uuid  # noqa: E402

BASE = dict(name="Daily", template_id=uuid.uuid4(), seed_campaign_id=uuid.uuid4(), start_on="2026-10-06")


def test_auto_in_defaults_match_the_spec():
    a = r.AutoIn(**BASE)
    assert (a.every_days, a.run_at, a.cooldown_days, a.max_runs, a.rate_per_minute) == (1, "11:00", 7, None, 30)
    assert (a.send_window_start, a.send_window_end, a.repeat_mode) == ("10:00", "19:00", "non_responders")
    assert a.start_on == date(2026, 10, 6)


@pytest.mark.parametrize("bad", [
    {"every_days": 0}, {"every_days": 91}, {"run_at": "9:00"}, {"run_at": "24:00"}, {"max_runs": 0},
    {"send_window_start": "19:00", "send_window_end": "10:00"}, {"repeat_mode": "nobody"}, {"start_on": "soon"},
    {"rate_per_minute": 0}, {"cooldown_days": -1},
])
def test_auto_in_refuses_bad_values(bad):
    with pytest.raises(ValidationError):
        r.AutoIn(**(BASE | bad))


def test_every_auto_route_is_above_the_cid_routes():
    """/wa-campaigns/auto read as /wa-campaigns/{cid} is a 422 on 'auto'."""
    routes = [(i, rt.path, rt.methods) for i, rt in enumerate(r.router.routes)]
    cid_at = min(i for i, p, _ in routes if p.startswith("/wa-campaigns/{cid}"))
    autos = [(i, p) for i, p, _ in routes if p.startswith("/wa-campaigns/auto")]
    assert len(autos) == 5, autos  # GET, POST, PATCH, dry-run, action
    assert all(i < cid_at for i, _ in autos), autos


def test_auto_endpoints_are_admin_only_and_never_put():
    for rt in r.router.routes:
        if rt.path.startswith("/wa-campaigns/auto"):
            assert "PUT" not in rt.methods
    assert any(d.dependency.__name__ == "require_admin" for d in r.router.dependencies)


def test_a_new_definition_is_created_inactive_and_the_seed_is_locked():
    assert "active=False" in inspect.getsource(r.create_auto)
    assert "seed campaign can't change" in inspect.getsource(r.edit_auto)


def test_activate_and_run_now_need_the_template_app_configured():
    src = inspect.getsource(r.auto_action)
    assert "gupshup_template_configured" in src and "503" in src
    assert "run_auto_campaigns(trigger=\"manual\"" in src


def test_the_list_carries_last_run_counts_and_a_status_note():
    src = inspect.getsource(r.list_autos)
    assert "last_run" in src and "status_note" in src and "FUNNEL_SQL" in src


# ── run_auto_campaigns, driven through a fake database (D-I4) ─────────────────────
# The fake answers each statement the service makes from a small in-memory state and records every statement with
# its params, so these tests assert what the code DOES — which slot it ran, what it wrote — not how its source reads.
from datetime import datetime, timedelta  # noqa: E402

from fastapi import HTTPException  # noqa: E402

from app.config import get_settings  # noqa: E402

TODAY = date(2026, 10, 5)
ADMIN = {"email": "a@openhouse.in", "name": "Admin", "role": "admin"}


class _Res:
    def __init__(self, rows=(), scalar=None):
        self.rows, self._scalar = list(rows), scalar

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def scalar(self):
        return self._scalar

    def __iter__(self):
        return iter(self.rows)


class _DB:
    """One definition + what the run code reads about it. `rows` = what auto_list returns (the classified list)."""

    def __init__(self, *, now=datetime(2026, 10, 5, 11, 30), last=None, seed_status="done", runs=0, rows=None,
                 conflict=False, locked_out=False, **a):
        self.a = {"id": uuid.uuid4(), "name": "Daily", "template_id": uuid.uuid4(), "seed_campaign_id": uuid.uuid4(),
                  "repeat_mode": "everyone", "every_days": 1, "run_at": "11:00", "next_slot": TODAY,
                  "cooldown_days": 7, "max_runs": None, "send_window_start": "10:00", "send_window_end": "19:00",
                  "rate_per_minute": 30, "active": True, **a}
        self.now, self.last, self.seed_status, self.runs = now, last, seed_status, runs
        self.rows = [{"phone10": "9876543210", "name": "R", "variables": ["x"], "status": "valid", "reason": None}] \
            if rows is None else rows
        self.conflict, self.locked_out, self.calls, self.log = conflict, locked_out, [], []
        self.auto_list_calls = []

    async def execute(self, stmt, params=None):
        self.calls.append((stmt, params))
        if stmt is svc.DUE_AUTO_SQL:
            return _Res([(self.a["id"],)] if self.a["active"] else [])
        if stmt is svc.ONE_AUTO_SQL:
            return _Res([(self.a["id"],)] if self.a["active"] else [])
        if stmt is svc.LOCK_AUTO_SQL:
            return _Res([] if self.locked_out or not self.a["active"] else [dict(self.a)])
        if stmt is svc.NOW_IST_SQL:
            return _Res(scalar=self.now)
        if stmt is svc.LAST_RUN_SQL:
            return _Res([self.last] if self.last else [])
        if stmt is svc.SOURCE_STATUS_SQL:
            return _Res(scalar=self.seed_status)
        if stmt is svc.RUN_COUNT_SQL:
            return _Res(scalar=self.runs)
        if stmt is svc.INSERT_RUN_SQL:
            if self.conflict:
                return _Res([])
            self.runs += 1
            return _Res([(params["id"],)])
        if stmt in (svc.FINISH_AUTO_SQL, svc.SKIP_SLOT_SQL, svc.ADVANCE_AUTO_SQL, svc.NOTE_AUTO_SQL):
            if stmt is svc.FINISH_AUTO_SQL:
                self.a["active"] = False
            if "n" in params:
                self.a["next_slot"] = params["n"]
            return _Res()
        return _Res()

    def ran(self, stmt):
        return [p for s, p in self.calls if s is stmt]

    def recipients(self):
        return [p for s, p in self.calls if getattr(getattr(s, "table", None), "name", "") == "wa_campaign_recipients"]


class _Ctx:
    def __init__(self, db, kind):
        self.db, self.kind = db, kind

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, et, e, tb):
        self.db.log.append((self.kind, "rollback" if et else "commit"))
        return False


class _Eng:
    def __init__(self, db):
        self.db = db

    def connect(self):
        return _Ctx(self.db, "connect")

    def begin(self):
        return _Ctx(self.db, "begin")


@pytest.fixture
def db(monkeypatch):
    """A fresh fake per test; neon_engine and auto_list point at it (the list itself is tested in test_wa_campaigns)."""
    holder = {}

    def use(**kw):
        d = _DB(**kw)
        holder["db"] = d
        monkeypatch.setattr(svc, "neon_engine", lambda: _Eng(d))

        async def fake_auto_list(conn, a, last):
            d.auto_list_calls.append((a["id"], last))
            return (last["id"] if last else a["seed_campaign_id"]), {"body": "Hi {{1}}"}, d.rows
        monkeypatch.setattr(svc, "auto_list", fake_auto_list)
        return d
    return use


async def test_a_due_slot_queues_a_sending_run_with_the_list_in_order_and_advances(db):
    d = db(rows=[{"phone10": f"98765432{i:02d}", "name": None, "variables": ["x"], "status": s,
                  "reason": None if s == "valid" else "cooldown"} for i, s in enumerate(["valid", "skipped", "valid"])])
    res = await svc.run_auto_campaigns()
    assert res == {"status": "ok", "runs": 1, "skipped": [], "failed": []}
    [ins] = d.ran(svc.INSERT_RUN_SQL)
    assert ins["slot"] == TODAY and ins["name"] == "Daily · 5 Oct" and ins["repeat_of"] == d.a["seed_campaign_id"]
    [rows] = d.recipients()
    assert [(x["position"], x["status"], x["skip_reason"]) for x in rows] == [
        (0, "queued", None), (1, "skipped", "cooldown"), (2, "queued", None)]
    assert d.ran(svc.ADVANCE_AUTO_SQL) == [{"n": TODAY + timedelta(days=1), "id": d.a["id"]}]   # ADVANCE mutant
    assert ("begin", "commit") in d.log


def test_a_run_is_inserted_as_sending_by_the_cron_and_one_per_slot():
    """A run inserted as 'draft' would never be sent (the loop only sends 'sending')."""
    sql = " ".join(svc.INSERT_RUN_SQL.text.split())
    assert "VALUES (:id, :name, :template_id, 'auto', :repeat_of, :aid, :slot, 'sending', 'cron', now(), :ws, :we, :rate)" in sql


def test_a_definition_is_due_once_its_slot_and_time_have_passed_and_the_lock_rechecks_it():
    assert svc.DUE_CLAUSE == "(a.next_slot + CAST(a.run_at AS time)) <= (now() AT TIME ZONE 'Asia/Kolkata')"
    assert svc.DUE_CLAUSE in svc.DUE_AUTO_SQL.text
    lock = " ".join(svc.LOCK_AUTO_SQL.text.split())
    assert f"WHERE a.id = :id AND a.active AND t.active AND (CAST(:manual AS boolean) OR {svc.DUE_CLAUSE}) FOR UPDATE OF a" in lock


@pytest.mark.parametrize("last,seed,why", [
    ({"id": uuid.uuid4(), "status": "sending"}, "done", "previous run still sending"),
    ({"id": uuid.uuid4(), "status": "paused"}, "done", "previous run is paused"),
    (None, "sending", "seed campaign still sending"),     # D-C1: run 1 copied a seed still going out
    (None, "paused", "seed campaign is paused"),
    (None, "draft", "seed campaign is draft"),
])
async def test_a_list_that_has_not_finished_going_out_is_never_copied(db, last, seed, why):
    d = db(last=last, seed_status=seed)
    res = await svc.run_auto_campaigns()
    assert res["runs"] == 0 and res["skipped"] == [{"auto": str(d.a["id"]), "reason": why}]
    assert not d.ran(svc.INSERT_RUN_SQL) and d.auto_list_calls == []
    assert d.ran(svc.SKIP_SLOT_SQL) == [{"n": TODAY + timedelta(days=1), "id": d.a["id"],
                                         "note": f"skipped 5 Oct: {why}"}]   # D-M4: the slot says why


async def test_a_refused_run_now_writes_nothing_and_keeps_the_scheduled_slot(db):
    """D-M1: Run now refused because the previous run is still sending must not throw today's slot away."""
    d = db(last={"id": uuid.uuid4(), "status": "sending"}, next_slot=TODAY)
    res = await svc.run_auto_campaigns(trigger="manual", only=d.a["id"])
    assert res["runs"] == 0 and res["skipped"][0]["reason"] == "previous run still sending"
    assert not d.ran(svc.SKIP_SLOT_SQL) and not d.ran(svc.ADVANCE_AUTO_SQL) and d.a["next_slot"] == TODAY


async def test_run_now_runs_todays_slot_whatever_next_slot_says(db):
    d = db(next_slot=TODAY + timedelta(days=3), now=datetime(2026, 10, 5, 8, 0))
    res = await svc.run_auto_campaigns(trigger="manual", only=d.a["id"])
    assert res["runs"] == 1 and d.ran(svc.INSERT_RUN_SQL)[0]["slot"] == TODAY
    assert d.ran(svc.LOCK_AUTO_SQL)[0] == {"id": d.a["id"], "manual": True}


async def test_the_cron_reads_the_locked_row_not_the_listed_one(db):
    """D-M1: the cron and Run now can't both run it — the second, behind the lock, finds it no longer due."""
    d = db(locked_out=True)
    res = await svc.run_auto_campaigns()
    assert res["runs"] == 0 and res["skipped"][0]["reason"] == "no longer due"
    assert d.ran(svc.LOCK_AUTO_SQL) == [{"id": d.a["id"], "manual": False}] and not d.ran(svc.INSERT_RUN_SQL)


async def test_a_missed_stretch_runs_once_for_the_latest_due_slot(db):
    """D-M2: cron down 2 → 5 Oct: one run named '5 Oct' (not '2 Oct'), next slot tomorrow."""
    d = db(next_slot=date(2026, 10, 2), now=datetime(2026, 10, 5, 12, 0))
    await svc.run_auto_campaigns()
    assert d.ran(svc.INSERT_RUN_SQL)[0]["slot"] == TODAY and d.ran(svc.INSERT_RUN_SQL)[0]["name"] == "Daily · 5 Oct"
    assert d.ran(svc.ADVANCE_AUTO_SQL)[0]["n"] == TODAY + timedelta(days=1)


def test_the_latest_due_slot_respects_run_at_and_the_schedule():
    f = svc.latest_due_slot
    assert f(date(2026, 10, 2), 1, "11:00", datetime(2026, 10, 5, 12, 0)) == date(2026, 10, 5)
    assert f(date(2026, 10, 2), 1, "11:00", datetime(2026, 10, 5, 9, 0)) == date(2026, 10, 4), "today's not due yet"
    assert f(date(2026, 9, 28), 7, "11:00", datetime(2026, 10, 5, 12, 0)) == date(2026, 10, 5)
    assert f(date(2026, 9, 28), 7, "11:00", datetime(2026, 10, 5, 9, 0)) == date(2026, 9, 28)
    assert f(TODAY, 1, "11:00", datetime(2026, 10, 5, 11, 0)) == TODAY, "on time"


def test_a_slot_whose_time_has_come_rolls_forward():
    f = svc.roll_forward
    assert f(date(2026, 10, 2), 1, "11:00", datetime(2026, 10, 5, 9, 0)) == date(2026, 10, 5), "today 11:00 is ahead"
    assert f(date(2026, 10, 2), 1, "11:00", datetime(2026, 10, 5, 14, 0)) == date(2026, 10, 6)
    assert f(date(2026, 9, 28), 7, "11:00", datetime(2026, 10, 5, 14, 0)) == date(2026, 10, 12)
    assert f(date(2026, 10, 9), 1, "11:00", datetime(2026, 10, 5, 14, 0)) == date(2026, 10, 9), "future: untouched"


@pytest.mark.parametrize("runs,max_runs,inserted", [(1, 2, True), (2, 2, False), (0, 1, True)])
async def test_max_runs_stops_the_definition_right_after_its_last_run(db, runs, max_runs, inserted):
    """D-M3: the max_runs-th run finishes the definition at once — not a dead 'next run' on the list."""
    d = db(runs=runs, max_runs=max_runs)
    await svc.run_auto_campaigns()
    assert bool(d.ran(svc.INSERT_RUN_SQL)) is inserted
    assert d.ran(svc.FINISH_AUTO_SQL) == [{"id": d.a["id"], "note": "finished — max runs reached"}]
    assert not d.ran(svc.ADVANCE_AUTO_SQL) and d.a["active"] is False


async def test_an_empty_list_finishes_the_definition(db):
    d = db(rows=[])
    res = await svc.run_auto_campaigns()
    assert res["skipped"][0]["reason"] == "no one left to message" and not d.ran(svc.INSERT_RUN_SQL)
    assert d.ran(svc.FINISH_AUTO_SQL) == [{"id": d.a["id"], "note": "finished — no one left to message"}]


async def test_an_all_skipped_list_skips_the_slot_and_keeps_the_definition(db):
    """D-I1: a cooldown skip is transient — finishing on it ended the campaign for good."""
    d = db(rows=[{"phone10": "9876543210", "name": None, "variables": [], "status": "skipped", "reason": "cooldown"},
                 {"phone10": "9876543211", "name": None, "variables": [], "status": "skipped", "reason": "cooldown"},
                 {"phone10": "9876543212", "name": None, "variables": [], "status": "skipped", "reason": "opted_out"}])
    res = await svc.run_auto_campaigns()
    assert res["skipped"][0]["reason"] == "everyone was skipped (cooldown 2, opted_out 1)"
    assert not d.ran(svc.INSERT_RUN_SQL) and not d.ran(svc.FINISH_AUTO_SQL) and d.a["active"] is True
    assert d.ran(svc.SKIP_SLOT_SQL) == [{"n": TODAY + timedelta(days=1), "id": d.a["id"],
                                         "note": "skipped 5 Oct: everyone was skipped (cooldown 2, opted_out 1)"}]


async def test_a_slot_that_already_ran_is_skipped_with_a_note(db):
    d = db(conflict=True)
    res = await svc.run_auto_campaigns()
    assert res["skipped"][0]["reason"] == "this slot already ran" and not d.recipients()
    assert d.ran(svc.SKIP_SLOT_SQL)[0]["note"] == "skipped 5 Oct: this slot already ran"


async def test_one_failing_definition_is_noted_and_reported_and_the_rest_still_run(db, monkeypatch):
    """D-I3: an exception used to escape the loop — every healthy definition got 0 runs every 15 min."""
    d = db()
    good, bad = d.a["id"], uuid.uuid4()
    real_execute = d.execute

    async def execute(stmt, params=None):
        if stmt is svc.DUE_AUTO_SQL:
            return _Res([(bad,), (good,)])
        if stmt is svc.LOCK_AUTO_SQL and params["id"] == bad:
            raise ValueError("template has 2 variable(s), got 1")
        return await real_execute(stmt, params)
    monkeypatch.setattr(d, "execute", execute)
    res = await svc.run_auto_campaigns()
    assert res["runs"] == 1 and res["failed"] == [{"auto": str(bad), "error": "ValueError: template has 2 variable(s), got 1"}]
    assert d.ran(svc.NOTE_AUTO_SQL) == [{"id": bad, "note": "error: ValueError: template has 2 variable(s), got 1"}]
    assert ("begin", "rollback") in d.log, "the failed definition's own transaction rolled back"


async def test_the_cron_task_exits_non_zero_when_a_definition_failed(monkeypatch):
    import importlib.util
    import pathlib
    p = pathlib.Path(__file__).parents[1] / "scripts" / "20_cron_tasks.py"
    spec = importlib.util.spec_from_file_location("cron", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    async def fake(trigger):
        return {"status": "ok", "runs": 1, "skipped": [], "failed": [{"auto": "x", "error": "boom"}]}
    monkeypatch.setattr(svc, "run_auto_campaigns", fake)
    with pytest.raises(RuntimeError, match="1 auto campaign"):
        await m.task_wa_auto()


# ── the router's auto actions, against the same fake ─────────────────────────────
@pytest.fixture
def configured(monkeypatch):
    s = get_settings()
    for k, v in (("GUPSHUP_TEMPLATE_API_KEY", "k"), ("GUPSHUP_TEMPLATE_SOURCE_NUMBER", "918888888888"),
                 ("GUPSHUP_TEMPLATE_APP_NAME", "OHTemplates")):
        monkeypatch.setattr(s, k, v)


class _RouterDB(_DB):
    """The router reads the definition through select(WaAutoCampaign) and the template's active flag."""

    async def execute(self, stmt, params=None):
        text_ = str(stmt)
        if "FROM wa_auto_campaigns" in text_ and "wa_auto_campaigns.id = " in text_ and stmt is not svc.LOCK_AUTO_SQL:
            self.calls.append((stmt, params))
            return _Res([dict(self.a)])
        if "wa_templates.active" in text_ and "FROM wa_templates" in text_:
            self.calls.append((stmt, params))
            return _Res([(True,)])
        return await super().execute(stmt, params)


async def test_run_now_on_a_switched_off_definition_is_refused_before_anything_runs(monkeypatch, configured):
    d = _RouterDB(active=False)
    monkeypatch.setattr(r, "_engine", lambda: _Eng(d))
    called = []

    async def run(**kw):
        called.append(kw)
        return {"runs": 1}
    monkeypatch.setattr(svc, "run_auto_campaigns", run)
    with pytest.raises(HTTPException) as e:
        await r.auto_action(d.a["id"], "run-now", ADMIN)
    assert e.value.status_code == 409 and "switch the auto campaign on first" in e.value.detail and called == []
    assert " a.active " in " ".join(svc.ONE_AUTO_SQL.text.split()) + " "


async def test_activating_rolls_a_slot_that_has_passed_forward(monkeypatch, configured):
    """D-M2: switched on at 14:00 with today's 11:00 slot gone — the next run is tomorrow, not right now."""
    d = _RouterDB(active=False, next_slot=date(2026, 10, 2), now=datetime(2026, 10, 5, 14, 0))
    monkeypatch.setattr(r, "_engine", lambda: _Eng(d))
    assert await r.auto_action(d.a["id"], "activate", ADMIN) == {"status": "active"}
    [upd] = [s for s, _ in d.calls if getattr(s, "is_update", False)]
    assert upd.compile().params["next_slot"] == date(2026, 10, 6) and upd.compile().params["active"] is True


async def test_a_run_now_that_failed_says_why(monkeypatch, configured):
    d = _RouterDB()
    monkeypatch.setattr(r, "_engine", lambda: _Eng(d))

    async def run(**kw):
        return {"status": "ok", "runs": 0, "skipped": [], "failed": [{"auto": "x", "error": "ValueError: bad"}]}
    monkeypatch.setattr(svc, "run_auto_campaigns", run)
    with pytest.raises(HTTPException) as e:
        await r.auto_action(d.a["id"], "run-now", ADMIN)
    assert e.value.status_code == 409 and e.value.detail == "No run was started — error: ValueError: bad"


# ── the dry run (shared contract: POST /wa-campaigns/auto/dry-run, body = AutoIn) ──────
def test_the_dry_run_route_is_literal_and_takes_the_form_not_an_id():
    paths = [(rt.path, rt.methods) for rt in r.router.routes]
    assert ("/wa-campaigns/auto/dry-run", {"POST"}) in paths
    assert not any(p == "/wa-campaigns/auto/{aid}/dry-run" for p, _ in paths), "the per-id dry run is gone"
    assert paths.index(("/wa-campaigns/auto/dry-run", {"POST"})) < paths.index(("/wa-campaigns/{cid}/{action}", {"POST"}))
    assert inspect.signature(r.dry_run_auto).parameters["a"].annotation is r.AutoIn


async def test_the_dry_run_counts_the_next_list_warns_over_the_daily_limit_and_writes_nothing(monkeypatch):
    monkeypatch.setattr(get_settings(), "WA_DAILY_SEND_LIMIT", 1)
    seed, last_run = uuid.uuid4(), uuid.uuid4()
    rows = [{"phone10": "98765432%02d" % i, "name": None, "variables": ["Ravi"], "status": "valid", "reason": None}
            for i in range(2)] + [{"phone10": "9876543299", "name": None, "variables": ["x"], "status": "skipped",
                                   "reason": "cooldown"}]
    seen, calls = [], []

    async def fake_auto_list(conn, a, last):
        seen.append((a, last))
        return last["id"], {"body": "Hi {{1}}"}, rows
    monkeypatch.setattr(svc, "auto_list", fake_auto_list)

    class _C:
        async def execute(self, stmt, params=None):
            calls.append(stmt)
            return _Res([{"id": last_run, "status": "done"}])
    out = await svc.auto_dry_run(_C(), {"seed_campaign_id": seed, "template_id": uuid.uuid4(),
                                        "repeat_mode": "everyone", "cooldown_days": 7})
    assert out == {"counts": {"valid": 2, "invalid": 0, "duplicate": 0, "skipped": 1},
                   "samples": ["Hi Ravi", "Hi Ravi"], "over_daily_limit": True, "daily_limit": 1}
    assert calls == [svc.SEED_LAST_RUN_SQL] and seen[0][1]["id"] == last_run, "the next run repeats the last run"


async def test_the_dry_run_endpoint_checks_the_form_and_only_connects(monkeypatch):
    d = _DB()
    eng = _Eng(d)
    monkeypatch.setattr(r, "_engine", lambda: eng)
    checked = []

    async def check(conn, a):
        checked.append(a)
    monkeypatch.setattr(r, "_check_auto", check)

    async def dry(conn, a):
        return {"counts": {}, "samples": [], "over_daily_limit": False, "daily_limit": 250}
    monkeypatch.setattr(svc, "auto_dry_run", dry)
    a = r.AutoIn(**BASE)
    assert (await r.dry_run_auto(a))["daily_limit"] == 250 and checked == [a]
    assert d.log == [("connect", "commit")], "a read: connect(), never begin()"


async def test_a_draft_seed_is_refused(monkeypatch):
    """D-C1: an auto campaign on a seed that hasn't gone out would copy it while it sends."""
    class _C:
        async def execute(self, stmt, params=None):
            if stmt is svc.SOURCE_CAMPAIGN_SQL:
                return _Res([{"id": params["campaign_id"], "status": "draft", "variable_count": 1}])
            return _Res([{"id": uuid.uuid4(), "active": True, "variable_count": 1}])
    with pytest.raises(HTTPException) as e:
        await r._check_auto(_C(), r.AutoIn(**BASE))
    assert e.value.status_code == 422 and "draft" in e.value.detail
    assert "c.status" in svc.SOURCE_CAMPAIGN_SQL.text


async def test_an_auto_campaigns_template_is_locked_like_a_used_one(monkeypatch):
    """D-I3: a template edited to a new slot count poisoned the auto definition that sends it."""
    sql = str(r._used_by_anything(uuid.uuid4()).compile())
    assert "wa_campaigns.template_id" in sql and "wa_auto_campaigns.template_id" in sql
    assert "_used_by_anything(WaTemplate.id)" in inspect.getsource(r.list_templates)
    assert "_used_by_anything(template_id)" in inspect.getsource(r.edit_template)
