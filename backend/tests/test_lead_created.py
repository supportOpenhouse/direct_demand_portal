"""`lead_created` is written by the database (scripts/lead_created_trigger.sql), for
every lead from every source — including the Apps Script, which never runs Python.

An app-side `action="lead_created"` as well would log each such lead twice and double
the Reports page's created counts, so no app module may write one.
"""
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def test_no_app_code_writes_lead_created():
    # a Python keyword argument only — `(?<![.\w])` skips SQL such as the historical
    # backfill's `a.action = 'lead_created'`, which reads the entries, not writes one
    pattern = re.compile(r"""(?<![.\w])action\s*=\s*["']lead_created["']""")
    hits = [str(p.relative_to(APP)) for p in APP.rglob("*.py") if pattern.search(p.read_text())]
    assert hits == [], f"lead_created is the DB trigger's job, found in: {hits}"


def test_the_trigger_takes_the_actor_from_source_meta():
    """Without it every hand-made lead (WhatsApp, Huvo, Add lead) loses who made it."""
    sql = (APP.parent / "scripts" / "lead_created_trigger.sql").read_text()
    assert "AFTER INSERT ON leads" in sql
    assert "source_meta->>'created_by'" in sql
