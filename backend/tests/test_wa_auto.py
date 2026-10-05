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


def test_a_still_sending_previous_run_skips_the_slot():
    src = inspect.getsource(svc.run_auto_campaigns)
    assert "'sending'" in src.replace('"', "'") and "skipped" in src


def test_auto_cooldown_ignores_the_whole_family():
    """A daily auto with a 7-day cooldown must not empty itself on run 3 because run 1
    reached everyone 2 days ago: the seed and all its own runs are ignored (spec §4.4)."""
    src = inspect.getsource(svc.auto_list)
    assert "seed_campaign_id" in src and "REPEAT_FAMILY_SQL" in src and "ignore_campaigns=family" in src
    assert "auto_list(" in inspect.getsource(svc.run_auto_campaigns)


def test_the_dry_run_uses_the_same_list_builder_and_writes_nothing():
    src = inspect.getsource(svc.auto_dry_run)
    assert "auto_list(" in src
    assert not any(w in src.upper() for w in ("INSERT", "UPDATE ", "DELETE", "COMMIT"))


def test_an_auto_run_keeps_the_seed_lists_order_and_finishes_when_nobody_is_left():
    src = inspect.getsource(svc.run_auto_campaigns)
    assert '"position": i' in src
    assert "finished — no one left to message" in src and "finished — max runs reached" in src


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
