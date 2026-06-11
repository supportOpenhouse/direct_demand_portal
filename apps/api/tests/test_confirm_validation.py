"""POST /v1/leads/{id}/confirm — §6.6 mandatory-field validation + success effects."""

FULL_PAYLOAD = {
    "purpose": "self_use",
    "budget_value_lacs": 95,
    "configuration": "2 BHK",
    "shortlist_societies": ["DLF The Crest", "Ireo Skyon"],
    "preferred_localities": ["Golf Course Road"],
    "office_willing": "maybe",
    "office_preferred_date": "2026-06-20",
    "remark": "Serious buyer, call Saturday",
}
MANDATORY = ("purpose", "budget_value_lacs", "configuration", "office_willing")


async def test_empty_body_lists_every_missing_mandatory_field(client, auth, users, make_lead):
    lead = await make_lead(assigned_to=users.rm1.id)
    r = await client.post(f"/v1/leads/{lead.id}/confirm", json={}, headers=auth(users.rm1))
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]
    assert set(body["fields"].keys()) == set(MANDATORY)


async def test_each_single_missing_field_is_reported(client, auth, users, make_lead):
    for field in MANDATORY:
        lead = await make_lead(assigned_to=users.rm1.id)
        payload = {k: v for k, v in FULL_PAYLOAD.items() if k != field}
        r = await client.post(f"/v1/leads/{lead.id}/confirm", json=payload, headers=auth(users.rm1))
        assert r.status_code == 422, f"{field}: {r.text}"
        assert set(r.json()["fields"].keys()) == {field}


async def test_nonpositive_budget_rejected(client, auth, users, make_lead):
    lead = await make_lead(assigned_to=users.rm1.id)
    payload = dict(FULL_PAYLOAD, budget_value_lacs=0)
    r = await client.post(f"/v1/leads/{lead.id}/confirm", json=payload, headers=auth(users.rm1))
    assert r.status_code == 422
    assert "budget_value_lacs" in r.json()["fields"]


async def test_success_sets_confirmed_qualified_stage_tat_activity(client, auth, users, make_lead):
    lead = await make_lead(assigned_to=users.rm1.id, stage="new", confirmed=False)
    r = await client.post(f"/v1/leads/{lead.id}/confirm", json=FULL_PAYLOAD, headers=auth(users.rm1))
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["confirmed"] is True
    assert body["qualified_at"] is not None
    assert body["stage"] == "contacted"  # new -> contacted
    assert body["tat"] == {"state": None, "deadline": None, "minutes_left": None}  # TAT cleared

    conf = body["confirmed_data"]
    assert conf["purpose"] == "self_use"
    assert conf["budget_value_lacs"] == 95
    assert conf["configuration"] == "2 BHK"
    assert conf["office_willing"] == "maybe"
    assert conf["office_preferred_date"] == "2026-06-20"
    assert conf["confirmed_at"] is not None

    assert sorted(body["shortlist_societies"]) == ["DLF The Crest", "Ireo Skyon"]
    assert body["preferred_localities"] == ["Golf Course Road"]
    assert any(a["event"] == "confirmed" for a in body["activity"])

    # and it now appears in the qualified segment
    seg = await client.get("/v1/leads?segment=qualified", headers=auth(users.rm1))
    assert str(lead.id) in {item["id"] for item in seg.json()["items"]}


async def test_stage_change_requires_remark(client, auth, users, make_lead):
    lead = await make_lead(assigned_to=users.rm1.id, stage="contacted")
    r = await client.post(
        f"/v1/leads/{lead.id}/stage", json={"to_stage": "negotiation"}, headers=auth(users.rm1)
    )
    assert r.status_code == 422
    assert "remark" in r.json()["fields"]

    r = await client.post(
        f"/v1/leads/{lead.id}/stage",
        json={"to_stage": "negotiation", "remark": "buyer pushing on price"},
        headers=auth(users.rm1),
    )
    assert r.status_code == 200
    assert r.json()["stage"] == "negotiation"
    assert any(a["event"] == "stage_changed" for a in r.json()["activity"])
