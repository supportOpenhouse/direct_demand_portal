"""The send loop and campaign state changes, run against a scripted fake engine (no DB, no network).
neon_engine is patched in every test that could reach it: backend/.env points at PRODUCTION."""
import inspect
import uuid

import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.routers import wa_campaigns as r
from app.services import activity, gupshup_template, wa_assign
from app.services import wa_campaigns as svc

ADMIN = {"email": "a@openhouse.in", "name": "Admin", "role": "admin"}


class _Res:
    def __init__(self, rows=(), scalar=None, rowcount=1):
        self.rows, self._scalar, self.rowcount = list(rows), scalar, rowcount

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def scalar(self):
        return self._scalar

    def __iter__(self):
        return iter(self.rows)


class _Conn:
    def __init__(self, script):
        self.script, self.calls = script, []

    async def execute(self, stmt, params=None):
        self.calls.append((stmt, params))
        return self.script(stmt, params)


class _Ctx:
    def __init__(self, conn, log, kind):
        self.conn, self.log, self.kind = conn, log, kind

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, et, e, tb):
        self.log.append((self.kind, "rollback" if et else "commit"))
        return False


class _Engine:
    def __init__(self, script):
        self.conn, self.log = _Conn(script), []

    def connect(self):
        return _Ctx(self.conn, self.log, "connect")

    def begin(self):
        return _Ctx(self.conn, self.log, "begin")

    def ran(self, stmt):
        return [p for s, p in self.conn.calls if s is stmt]


CAMP = {"id": uuid.uuid4(), "rate_per_minute": 60, "gupshup_template_id": "tpl", "body": "Hi {{1}}",
        "template_name": "T", "created_by": "a@openhouse.in"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "GUPSHUP_TEMPLATE_API_KEY", "k")
    monkeypatch.setattr(s, "GUPSHUP_TEMPLATE_SOURCE_NUMBER", "918888888888")
    monkeypatch.setattr(s, "GUPSHUP_TEMPLATE_APP_NAME", "OHTemplates")
    monkeypatch.setattr(s, "WA_DAILY_SEND_LIMIT", 250)
    monkeypatch.setattr(svc, "neon_engine", lambda: None)  # nothing may reach the real engine by accident
    monkeypatch.setattr(svc, "_backoff_until", 0.0)
    svc._carry.clear()

    async def no_owner(conn, p10):
        return "Asha"
    monkeypatch.setattr(wa_assign, "assign_if_unassigned", no_owner)

    async def no_http(*a, **k):
        raise AssertionError("a test reached Gupshup without scripting send_template")
    monkeypatch.setattr(gupshup_template, "send_template", no_http)


def _script(*, claim=True, due=(CAMP,), sent=0, queued=("rid1",), accepted_rows=1):
    def f(stmt, p):
        if stmt is svc.ACCEPTED_SQL:
            return _Res(rowcount=accepted_rows)
        if stmt is svc.DUE_SQL:
            return _Res(due)
        if stmt is svc.SENT_24H_SQL:
            return _Res(scalar=sent)
        if stmt is svc.NEXT_QUEUED_SQL:
            return _Res([(q,) for q in queued][: p["n"]])
        if stmt is svc.CLAIM_SQL:
            return _Res([{"id": p["id"], "phone10": "9876543210", "variables": ["Rahul"]}] if claim else [])
        return _Res()
    return f


def _use(monkeypatch, script):
    eng = _Engine(script)
    monkeypatch.setattr(svc, "neon_engine", lambda: eng)
    return eng


def _scripted_send(monkeypatch, result):
    sent = []

    async def fake(phone10, tpl, params):
        sent.append((phone10, tpl, params))
        return result
    monkeypatch.setattr(gupshup_template, "send_template", fake)
    return sent


async def test_an_accepted_send_marks_accepted_and_writes_the_template_bubble(monkeypatch):
    eng = _use(monkeypatch, _script())
    sent = _scripted_send(monkeypatch, {"ok": True, "message_id": "m1"})
    assert await svc.tick() == 1
    assert sent == [("9876543210", "tpl", ["Rahul"])]
    assert eng.ran(svc.ACCEPTED_SQL) == [{"g": "m1", "id": "rid1"}]
    assert eng.ran(svc.SET_OWNER_SQL) == [{"o": "Asha", "id": "rid1"}]
    msg = [s for s, _ in eng.conn.calls if getattr(getattr(s, "table", None), "name", "") == "wa_messages"]
    assert len(msg) == 1 and msg[0].compile().params["source_app"] == "template"
    assert msg[0].compile().params["body"] == "Hi Rahul"
    assert eng.ran(svc.FINISH_SQL) == [{"cid": CAMP["id"]}]


async def test_a_broken_template_body_never_rolls_back_the_accepted_write(monkeypatch):
    eng = _use(monkeypatch, _script(due=({**CAMP, "body": "Hi {{1}} {{2}}"},)))
    _scripted_send(monkeypatch, {"ok": True, "message_id": "m1"})
    await svc.tick()
    assert eng.ran(svc.ACCEPTED_SQL) and ("begin", "rollback") not in eng.log


async def test_a_429_requeues_and_backs_the_whole_loop_off(monkeypatch):
    eng = _use(monkeypatch, _script(queued=("a", "b")))
    sent = _scripted_send(monkeypatch, {"ok": False, "error": "Too Many Requests", "retry": True})
    assert await svc.tick() == 1 and len(sent) == 1, "stops at the first refusal"
    assert eng.ran(svc.REQUEUE_SQL) == [{"id": "a"}] and not eng.ran(svc.FINISH_SQL)
    assert await svc.tick() == 0 and len(sent) == 1, "backed off"


async def test_a_refused_send_is_failed_with_gupshups_text_and_the_batch_goes_on(monkeypatch):
    eng = _use(monkeypatch, _script(queued=("a", "b")))
    sent = _scripted_send(monkeypatch, {"ok": False, "error": "Invalid destination"})
    assert await svc.tick() == 2 and len(sent) == 2
    assert eng.ran(svc.FAILED_SQL)[0] == {"e": "Invalid destination", "id": "a"}


async def test_an_unknown_outcome_leaves_the_row_submitted_and_backs_the_loop_off(monkeypatch):
    """G-2: during an outage every send is "no answer". Without the back-off the loop turned the whole queue
    into "Unknown — check" at full rate; now it stops at the first one and waits BACKOFF_SECONDS."""
    eng = _use(monkeypatch, _script(queued=("a", "b", "c")))
    sent = _scripted_send(monkeypatch, {"ok": False, "error": "down", "unknown": True})
    assert await svc.tick() == 1 and len(sent) == 1, "stops at the first unknown"
    for sql in (svc.ACCEPTED_SQL, svc.FAILED_SQL, svc.REQUEUE_SQL, svc.FINISH_SQL):
        assert not eng.ran(sql)
    assert await svc.tick() == 0 and len(sent) == 1, "backed off"


async def test_a_connection_that_was_never_made_requeues_and_backs_off(monkeypatch):
    """G-2: ConnectError / ConnectTimeout / PoolTimeout — send_template says retry; the row goes back in line."""
    eng = _use(monkeypatch, _script(queued=("a", "b")))
    _scripted_send(monkeypatch, {"ok": False, "error": "couldn't reach Gupshup", "status": None, "retry": True})
    assert await svc.tick() == 1
    assert eng.ran(svc.REQUEUE_SQL) == [{"id": "a"}] and not eng.ran(svc.FAILED_SQL)
    assert await svc.tick() == 0


async def test_a_refusal_of_the_app_pauses_the_campaign_requeues_the_row_and_backs_off(monkeypatch):
    """G-3: 401 / 403 / "Invalid App Details" would fail every recipient one by one."""
    eng = _use(monkeypatch, _script(queued=("a", "b")))
    sent = _scripted_send(monkeypatch, {"ok": False, "error": "Invalid App Details", "status": 400, "account": True})
    assert await svc.tick() == 1 and len(sent) == 1
    assert eng.ran(svc.REQUEUE_SQL) == [{"id": "a"}] and not eng.ran(svc.FAILED_SQL)
    assert eng.ran(svc.PAUSE_SQL) == [{"cid": CAMP["id"],
                                       "note": "Paused: Gupshup refused the app credentials (400 Invalid App Details)"}]
    assert await svc.tick() == 0 and len(sent) == 1, "backed off"


async def test_the_message_id_is_logged_before_the_write_that_could_fail(monkeypatch, caplog):
    """G-2: if the accepted write fails, the log line is the only record tying the messageId to its recipient."""
    def script(stmt, p):
        if stmt is svc.ACCEPTED_SQL:
            raise RuntimeError("db down")
        return _script()(stmt, p)
    _use(monkeypatch, script)
    _scripted_send(monkeypatch, {"ok": True, "message_id": "m-77", "status": 202})
    with caplog.at_level("INFO", logger="wa_campaigns"), pytest.raises(RuntimeError):
        await svc.tick()
    assert "messageId=m-77" in caplog.text and "recipient=rid1" in caplog.text


async def test_an_accepted_write_that_matched_no_row_is_logged(monkeypatch, caplog):
    """G-7: the row was retried (or changed) while its send was in flight — say so, its receipts won't find it."""
    _use(monkeypatch, _script(accepted_rows=0))
    _scripted_send(monkeypatch, {"ok": True, "message_id": "m-9", "status": 202})
    with caplog.at_level("WARNING", logger="wa_campaigns"):
        await svc.tick()
    assert "m-9" in caplog.text and "no longer 'submitted'" in caplog.text


async def test_a_row_someone_else_claimed_or_opted_out_is_not_sent(monkeypatch):
    eng = _use(monkeypatch, _script(claim=False))
    sent = _scripted_send(monkeypatch, {"ok": True, "message_id": "m"})
    await svc.tick()
    assert sent == [] and eng.ran(svc.SKIP_OPTED_OUT_SQL) == [{"id": "rid1"}]


async def test_the_24h_cap_stops_the_loop(monkeypatch):
    eng = _use(monkeypatch, _script(sent=250))
    sent = _scripted_send(monkeypatch, {"ok": True, "message_id": "m"})
    assert await svc.tick() == 0 and sent == [] and not eng.ran(svc.NEXT_QUEUED_SQL)


async def test_the_cap_limits_the_batch_to_what_is_left(monkeypatch):
    _use(monkeypatch, _script(sent=249, queued=("a", "b", "c")))
    sent = _scripted_send(monkeypatch, {"ok": True, "message_id": "m"})
    assert await svc.tick() == 1 and len(sent) == 1


async def test_an_idle_tick_costs_one_query_and_skips_the_count(monkeypatch):
    eng = _use(monkeypatch, _script(due=()))
    assert await svc.tick() == 0
    assert not eng.ran(svc.SENT_24H_SQL)


async def test_unconfigured_tick_does_nothing(monkeypatch):
    eng = _use(monkeypatch, _script())
    monkeypatch.setattr(get_settings(), "GUPSHUP_TEMPLATE_APP_NAME", "")
    assert await svc.tick() == 0 and eng.conn.calls == []


def test_pacing_holds_the_rate_that_was_asked_for():
    """30/min is 2.5 sends per 5 s tick; 1/min is one send in twelve ticks. Per-tick rounding gave 24 and 12."""
    cid = uuid.uuid4()
    per_minute = lambda rate: sum(svc._quota(cid, rate) for _ in range(60 // svc.TICK_SECONDS))  # noqa: E731
    assert per_minute(30) == 30
    svc._carry.clear()
    assert per_minute(1) == 1
    svc._carry.clear()
    assert per_minute(600) == 600


async def test_set_status_returns_the_new_state_and_logs_it_in_the_past_tense():
    conn = _Conn(lambda s, p: _Res([("draft",)]) if "UPDATE wa_campaigns" in str(s) else _Res())
    assert await svc.set_status(conn, uuid.uuid4(), "launch", ADMIN) == "sending"
    assert "wa_campaign_launched" in repr([p for _, p in conn.calls if p])


async def test_set_status_refuses_a_wrong_state():
    conn = _Conn(lambda s, p: _Res())
    with pytest.raises(ValueError, match="can't pause"):
        await svc.set_status(conn, uuid.uuid4(), "pause", ADMIN)


def test_the_transitions():
    t = svc.TRANSITIONS
    assert t["launch"] == ({"draft"}, "sending") and t["resume"] == ({"paused"}, "sending")
    assert t["cancel"][0] == {"draft", "sending", "paused"} and t["pause"] == ({"sending"}, "paused")
    assert "launched_at IS NULL" in inspect.getsource(svc.set_status)


def _router_engine(monkeypatch, script):
    eng = _Engine(script)
    monkeypatch.setattr(r, "_engine", lambda: eng)
    return eng


async def test_launch_and_resume_503_naming_the_missing_vars_but_pause_and_cancel_still_work(monkeypatch):
    eng = _router_engine(monkeypatch, lambda s, p: _Res([("sending",)]))
    monkeypatch.setattr(get_settings(), "GUPSHUP_TEMPLATE_API_KEY", "")
    for action in ("launch", "resume"):
        with pytest.raises(HTTPException) as e:
            await r.campaign_action(uuid.uuid4(), action, ADMIN)
        assert e.value.status_code == 503 and "GUPSHUP_TEMPLATE_API_KEY" in e.value.detail
    assert eng.conn.calls == [], "refused before touching the database"
    assert await r.campaign_action(uuid.uuid4(), "pause", ADMIN) == {"status": "paused"}


async def test_a_state_conflict_is_a_409(monkeypatch):
    _router_engine(monkeypatch, lambda s, p: _Res())
    with pytest.raises(HTTPException) as e:
        await r.campaign_action(uuid.uuid4(), "cancel", ADMIN)
    assert e.value.status_code == 409


def _peek(**over):
    return {"error": "131026: x", "status": "failed", "status_at": None, "campaign_status": "done",
            "in_flight": False, **over}


async def test_retry_requeues_reopens_a_done_campaign_and_logs_it(monkeypatch):
    eng = _router_engine(monkeypatch, lambda s, p: _Res([_peek()]) if s is r.RETRY_PEEK_SQL else _Res([("x",)]))
    cid, rid = uuid.uuid4(), uuid.uuid4()
    assert await r.retry_recipient(cid, rid, ADMIN) == {"status": "queued"}
    assert eng.ran(r.REOPEN_SQL) and "status IN ('failed', 'submitted')" in r.RETRY_SQL.text
    assert "status = 'done'" in r.REOPEN_SQL.text
    logged = [row for s, p in eng.conn.calls if s is activity._INSERT for row in p
              if row["action"] == "wa_campaign_retry"]   # D-M6
    assert logged and logged[0]["entity_id"] == str(cid) and str(rid) in logged[0]["metadata"]


def test_a_retry_is_a_fresh_send_so_the_old_ids_go():
    """G-8: a stale receipt for the earlier attempt carried the old gupshup_id and moved the retried row."""
    sql = " ".join(r.RETRY_SQL.text.split())
    assert "SET status = 'queued', error = NULL, gupshup_id = NULL, whatsapp_id = NULL, status_at = now()" in sql


@pytest.mark.parametrize("peek,why", [
    ({"campaign_status": "cancelled"}, "cancelled"),                                   # D-M6
    ({"status": "submitted", "error": None, "in_flight": True}, "still sending"),      # G-7
])
async def test_retry_is_refused_before_anything_is_written(monkeypatch, peek, why):
    eng = _router_engine(monkeypatch, lambda s, p: _Res([_peek(**peek)]) if s is r.RETRY_PEEK_SQL else _Res([("x",)]))
    with pytest.raises(HTTPException) as e:
        await r.retry_recipient(uuid.uuid4(), uuid.uuid4(), ADMIN)
    assert e.value.status_code == 409 and why in e.value.detail
    assert not eng.ran(r.RETRY_SQL) and not eng.ran(r.REOPEN_SQL)


def test_a_submitted_row_younger_than_a_minute_is_in_flight_in_the_sql_too():
    """The peek decides the message; RETRY_SQL itself refuses too, so a race between the two can't double-send."""
    assert r.RETRY_GRACE == "60 seconds"
    assert "(r.status = 'submitted' AND r.status_at > now() - interval '60 seconds') AS in_flight" in r.RETRY_PEEK_SQL.text
    assert "AND NOT (status = 'submitted' AND status_at > now() - interval '60 seconds')" in r.RETRY_SQL.text
    assert "c.status AS campaign_status" in r.RETRY_PEEK_SQL.text


async def test_retry_refuses_a_row_that_is_not_failed_or_unknown(monkeypatch):
    eng = _router_engine(monkeypatch, lambda s, p: _Res())
    with pytest.raises(HTTPException) as e:
        await r.retry_recipient(uuid.uuid4(), uuid.uuid4(), ADMIN)
    assert e.value.status_code == 409 and not eng.ran(r.REOPEN_SQL)


def test_the_action_route_only_takes_the_four_verbs_and_sits_below_the_literal_routes():
    import typing
    assert set(typing.get_args(inspect.signature(r.campaign_action).parameters["action"].annotation)) == {
        "launch", "pause", "resume", "cancel"}
    paths = [(x.path, x.methods) for x in r.router.routes]
    i = paths.index(("/wa-campaigns/{cid}/{action}", {"POST"}))
    for lit in ("/wa-campaigns/templates", "/wa-campaigns/preview"):
        assert paths.index((lit, {"POST"})) < i


def test_the_sender_starts_once_and_stops_without_ever_running_the_loop(monkeypatch):
    made = []

    class _T:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    def fake_create_task(coro):
        made.append(coro.cr_code.co_name)
        coro.close()  # never run the loop: it would open the real engine
        return _T()
    monkeypatch.setattr(svc, "_task", None)
    monkeypatch.setattr(svc.asyncio, "create_task", fake_create_task)
    svc.start_campaign_sender()
    svc.start_campaign_sender()
    assert made == ["_loop"]
    t = svc._task
    svc.stop_campaign_sender()
    assert t.cancelled and svc._task is None


def test_main_starts_and_stops_the_sender_beside_the_dialer():
    from pathlib import Path
    src = (Path(__file__).parent.parent / "app" / "main.py").read_text()
    assert src.index("start_dialer()\n") < src.index("start_campaign_sender()")
    assert src.index("stop_dialer()\n") < src.index("stop_campaign_sender()")


async def test_retry_is_refused_for_an_opted_out_recipient_before_anything_is_written(monkeypatch):
    eng = _router_engine(monkeypatch, lambda s, p: _Res([_peek(error="131050: opted out")]))
    with pytest.raises(HTTPException) as e:
        await r.retry_recipient(uuid.uuid4(), uuid.uuid4(), ADMIN)
    assert e.value.status_code == 409 and "opted out" in e.value.detail
    assert not eng.ran(r.RETRY_SQL) and not eng.ran(r.REOPEN_SQL)


# ── campaign-level stop codes and resume (G-4, G-10) ─────────────────────────────
async def test_a_stop_code_after_the_queue_drained_still_notes_the_campaign_and_stops_its_auto():
    """G-4: receipts land seconds after the send, so a small list is often 'done' already — the reason must still be
    recorded, and the auto definition that would repeat the failure tomorrow is switched off with the same note."""
    aid = uuid.uuid4()
    cid = uuid.uuid4()

    def script(stmt, p):
        if stmt is svc.RECEIPT_SQL:
            return _Res([{"campaign_id": cid, "phone10": "9876543210"}])
        if stmt is svc.STOP_CAMPAIGN_SQL:
            return _Res([(aid,)])
        return _Res()
    conn = _Conn(script)
    ev = {"type": "failed", "gsId": "g1", "id": "w1", "payload": {"code": 132015, "reason": "Template paused"}}
    await svc.apply_receipt(conn, ev)
    note = "Paused by Gupshup error 132015: Template paused"
    assert [p for s, p in conn.calls if s is svc.STOP_CAMPAIGN_SQL] == [{"cid": cid, "note": note}]
    assert [p for s, p in conn.calls if s is svc.STOP_AUTO_SQL] == [{"aid": aid, "note": note}]
    sql = " ".join(svc.STOP_CAMPAIGN_SQL.text.split())
    assert "status = CASE WHEN status = 'sending' THEN 'paused' ELSE status END" in sql
    assert "WHERE id = :cid AND status IN ('sending', 'paused', 'done')" in sql and "RETURNING auto_campaign_id" in sql
    assert "active = false, status_note = :note" in svc.STOP_AUTO_SQL.text


async def test_a_manual_campaigns_stop_code_touches_no_auto_definition():
    def script(stmt, p):
        if stmt is svc.RECEIPT_SQL:
            return _Res([{"campaign_id": uuid.uuid4(), "phone10": "9876543210"}])
        if stmt is svc.STOP_CAMPAIGN_SQL:
            return _Res([(None,)])
        return _Res()
    conn = _Conn(script)
    await svc.apply_receipt(conn, {"type": "failed", "gsId": "g", "payload": {"code": 132015, "reason": "x"}})
    assert not [p for s, p in conn.calls if s is svc.STOP_AUTO_SQL]


async def test_resuming_clears_the_reason_it_was_paused():
    """G-10: a 'Paused by Gupshup error …' note outlived the resume and kept warning about a fixed problem."""
    conn = _Conn(lambda s, p: _Res([("paused",)]) if "UPDATE wa_campaigns" in str(s) else _Res())
    assert await svc.set_status(conn, uuid.uuid4(), "resume", ADMIN) == "sending"
    sql = " ".join(str(conn.calls[0][0]).split())
    assert "status_note = CASE WHEN :to = 'sending' THEN NULL ELSE status_note END" in sql
    assert conn.calls[0][1]["to"] == "sending"
