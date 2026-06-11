"""Server-side role scoping (HANDOVER §4): rm = own leads, cm = team RM leads,
admin = all; plus the hard 403s."""
import pytest_asyncio


@pytest_asyncio.fixture
async def three_leads(users, make_lead):
    l1 = await make_lead(assigned_to=users.rm1.id, name="Lead RM1")
    l2 = await make_lead(assigned_to=users.rm2.id, name="Lead RM2")
    l3 = await make_lead(assigned_to=users.rm3.id, name="Lead RM3")
    return l1, l2, l3


async def list_ids(client, auth, user) -> set[str]:
    r = await client.get("/v1/leads", headers=auth(user))
    assert r.status_code == 200, r.text
    return {item["id"] for item in r.json()["items"]}


async def test_rm_sees_only_own_leads(client, auth, users, three_leads):
    l1, l2, l3 = three_leads
    assert await list_ids(client, auth, users.rm1) == {str(l1.id)}


async def test_cm_sees_team_but_not_other_rms(client, auth, users, three_leads):
    l1, l2, l3 = three_leads
    ids = await list_ids(client, auth, users.cm)
    assert ids == {str(l1.id), str(l2.id)}  # rm1+rm2 in team, rm3 teamless
    assert str(l3.id) not in ids


async def test_admin_sees_all(client, auth, users, three_leads):
    l1, l2, l3 = three_leads
    assert await list_ids(client, auth, users.admin) == {str(l1.id), str(l2.id), str(l3.id)}


async def test_rm_cannot_patch_source_data(client, auth, users, three_leads):
    l1, _, _ = three_leads
    r = await client.patch(
        f"/v1/leads/{l1.id}/source-data", json={"city": "Noida"}, headers=auth(users.rm1)
    )
    assert r.status_code == 403


async def test_cm_cannot_patch_source_data(client, auth, users, three_leads):
    l1, _, _ = three_leads
    r = await client.patch(
        f"/v1/leads/{l1.id}/source-data", json={"city": "Noida"}, headers=auth(users.cm)
    )
    assert r.status_code == 403


async def test_admin_can_patch_source_data(client, auth, users, three_leads):
    l1, _, _ = three_leads
    r = await client.patch(
        f"/v1/leads/{l1.id}/source-data", json={"city": "Noida"}, headers=auth(users.admin)
    )
    assert r.status_code == 200
    assert r.json()["source_data"]["city"] == "Noida"
    assert r.json()["city"] == "Noida"  # denormalized lead.city kept in sync


async def test_rm_gets_403_on_goldmine(client, auth, users):
    assert (await client.get("/v1/buckets", headers=auth(users.rm1))).status_code == 403
    assert (await client.post("/v1/buckets/rematch", headers=auth(users.rm1))).status_code == 403
    # admin + cm are allowed
    assert (await client.get("/v1/buckets", headers=auth(users.cm))).status_code == 200
    assert (await client.get("/v1/buckets", headers=auth(users.admin))).status_code == 200


async def test_rm_gets_404_for_other_rms_lead(client, auth, users, three_leads):
    _, l2, _ = three_leads
    r = await client.get(f"/v1/leads/{l2.id}", headers=auth(users.rm1))
    assert r.status_code == 404
    # but the owner sees it
    assert (await client.get(f"/v1/leads/{l2.id}", headers=auth(users.rm2))).status_code == 200


async def test_cm_sees_team_lead_detail_but_not_outside(client, auth, users, three_leads):
    l1, _, l3 = three_leads
    assert (await client.get(f"/v1/leads/{l1.id}", headers=auth(users.cm))).status_code == 200
    assert (await client.get(f"/v1/leads/{l3.id}", headers=auth(users.cm))).status_code == 404


async def test_reminders_scoped_via_lead(client, auth, users, three_leads):
    l1, l2, _ = three_leads
    r = await client.post(
        "/v1/reminders",
        json={"lead_id": str(l1.id), "type": "follow_up", "due_at": "2026-06-12T10:00:00Z"},
        headers=auth(users.rm1),
    )
    assert r.status_code == 201
    # rm1 cannot create a reminder against rm2's lead
    r = await client.post(
        "/v1/reminders",
        json={"lead_id": str(l2.id), "type": "follow_up", "due_at": "2026-06-12T10:00:00Z"},
        headers=auth(users.rm1),
    )
    assert r.status_code == 404
    # rm2 sees no reminders; rm1 sees one
    assert (await client.get("/v1/reminders", headers=auth(users.rm2))).json() == []
    assert len((await client.get("/v1/reminders", headers=auth(users.rm1))).json()) == 1


async def test_users_and_settings_admin_only(client, auth, users):
    assert (await client.get("/v1/users", headers=auth(users.rm1))).status_code == 403
    assert (await client.get("/v1/users", headers=auth(users.cm))).status_code == 403
    assert (await client.get("/v1/users", headers=auth(users.admin))).status_code == 200
    assert (await client.get("/v1/settings", headers=auth(users.rm1))).status_code == 403
    r = await client.patch(
        "/v1/settings/integrations", json={"key": "meta", "enabled": True}, headers=auth(users.cm)
    )
    assert r.status_code == 403
    r = await client.patch(
        "/v1/settings/integrations", json={"key": "meta", "enabled": True}, headers=auth(users.admin)
    )
    assert r.status_code == 200


async def test_unauthenticated_401(client):
    assert (await client.get("/v1/leads")).status_code == 401
