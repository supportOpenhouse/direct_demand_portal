"""Segment boundaries (HANDOVER §6.3): qualified <7d, pipeline >=7d, terminal
stages excluded, converted = won only."""
from datetime import timedelta

from app.core.utils import utcnow


async def seg_ids(client, auth, user, segment: str) -> set[str]:
    r = await client.get(f"/v1/leads?segment={segment}", headers=auth(user))
    assert r.status_code == 200, r.text
    return {item["id"] for item in r.json()["items"]}


async def test_seven_day_boundary(client, auth, users, make_lead):
    now = utcnow()
    just_inside = await make_lead(
        assigned_to=users.rm1.id, stage="contacted", confirmed=True,
        qualified_at=now - timedelta(days=6, hours=23),
    )
    just_outside = await make_lead(
        assigned_to=users.rm1.id, stage="contacted", confirmed=True,
        qualified_at=now - timedelta(days=7, hours=1),
    )
    qualified = await seg_ids(client, auth, users.admin, "qualified")
    pipeline = await seg_ids(client, auth, users.admin, "pipeline")
    assert str(just_inside.id) in qualified
    assert str(just_inside.id) not in pipeline
    assert str(just_outside.id) in pipeline
    assert str(just_outside.id) not in qualified


async def test_terminal_stages_excluded_from_qualified_and_pipeline(client, auth, users, make_lead):
    now = utcnow()
    terminal_recent = {}
    terminal_old = {}
    for stage in ("won", "lost", "future_prospect", "timepass"):
        terminal_recent[stage] = await make_lead(
            assigned_to=users.rm1.id, stage=stage, confirmed=True,
            qualified_at=now - timedelta(days=2),
        )
        terminal_old[stage] = await make_lead(
            assigned_to=users.rm1.id, stage=stage, confirmed=True,
            qualified_at=now - timedelta(days=20),
        )
    qualified = await seg_ids(client, auth, users.admin, "qualified")
    pipeline = await seg_ids(client, auth, users.admin, "pipeline")
    for lead in list(terminal_recent.values()) + list(terminal_old.values()):
        assert str(lead.id) not in qualified
        assert str(lead.id) not in pipeline


async def test_new_segment_excludes_terminal_unconfirmed(client, auth, users, make_lead):
    fresh = await make_lead(assigned_to=users.rm1.id, stage="new", confirmed=False)
    contacted_unconfirmed = await make_lead(assigned_to=users.rm1.id, stage="contacted", confirmed=False)
    timepass_unconfirmed = await make_lead(assigned_to=users.rm1.id, stage="timepass", confirmed=False)
    new_ids = await seg_ids(client, auth, users.admin, "new")
    assert str(fresh.id) in new_ids
    assert str(contacted_unconfirmed.id) in new_ids  # unconfirmed + non-terminal
    assert str(timepass_unconfirmed.id) not in new_ids


async def test_converted_is_won_only(client, auth, users, make_lead):
    now = utcnow()
    won = await make_lead(
        assigned_to=users.rm1.id, stage="won", confirmed=True, qualified_at=now - timedelta(days=2)
    )
    lost = await make_lead(
        assigned_to=users.rm1.id, stage="lost", confirmed=True, qualified_at=now - timedelta(days=2)
    )
    nego = await make_lead(
        assigned_to=users.rm1.id, stage="negotiation", confirmed=True,
        qualified_at=now - timedelta(days=2),
    )
    converted = await seg_ids(client, auth, users.admin, "converted")
    assert converted == {str(won.id)}
    assert str(lost.id) not in converted
    assert str(nego.id) not in converted
