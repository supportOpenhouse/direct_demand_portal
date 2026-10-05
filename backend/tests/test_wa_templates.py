import time

import pytest

from app.services.wa_templates import LOCKED_FIELDS, locked_changes, normalize_template, render, variable_count


def test_variable_count_is_the_highest_slot():
    assert variable_count("Hi {{1}}, still looking in {{2}}?") == 2
    assert variable_count("No variables here") == 0
    assert variable_count("{{1}} and {{1}} again") == 1


def test_a_gap_in_the_slots_is_refused():
    # Review Focus #4: {{1}} … {{3}} with no {{2}} can never be filled
    with pytest.raises(ValueError, match=r"\{\{2\}\}"):
        variable_count("Hi {{1}}, see {{3}}")


def test_zero_slot_is_refused():
    with pytest.raises(ValueError, match=r"\{\{0\}\}"):
        variable_count("Hi {{0}}")


def test_large_slot_numbers_are_rejected_quickly():
    # {{1}} {{4000000}} should reject quickly without iterating to 4000000
    t = time.perf_counter()
    with pytest.raises(ValueError):
        variable_count("{{1}} {{4000000}}")
    assert time.perf_counter() - t < 0.05, "must reject without iterating through millions"


def test_render_fills_every_slot_in_order():
    assert render("Hi {{1}} from {{2}}, {{1}}!", ["Rahul", "Noida"]) == "Hi Rahul from Noida, Rahul!"


def test_render_refuses_the_wrong_number_of_values():
    with pytest.raises(ValueError):
        render("Hi {{1}} from {{2}}", ["Rahul"])


def test_render_never_reads_values_beyond_slot_count():
    # Ensure {{0}} raises before accessing values[-1]
    with pytest.raises(ValueError, match=r"\{\{0\}\}"):
        render("{{0}} {{1}}", ["x"])


def test_the_text_that_was_sent_is_locked_once_used():
    assert set(LOCKED_FIELDS) == {"body", "gupshup_template_id"}


def test_template_routes_are_admin_only():
    from app.core.auth import require_admin
    from app.routers import wa_campaigns
    deps = [d.dependency for d in wa_campaigns.router.dependencies]
    assert require_admin in deps, "every wa-campaigns route is admin-only (router-level)"


def test_normalize_template_requires_fields():
    with pytest.raises(ValueError, match="required"):
        normalize_template({"gupshup_template_id": "", "name": "Test", "body": "Hi"})
    with pytest.raises(ValueError, match="required"):
        normalize_template({"gupshup_template_id": "abc", "name": "", "body": "Hi"})
    with pytest.raises(ValueError, match="required"):
        normalize_template({"gupshup_template_id": "abc", "name": "Test", "body": ""})


def test_normalize_template_rejects_bad_gupshup_id():
    with pytest.raises(ValueError, match="Use the Gupshup template ID"):
        normalize_template({
            "gupshup_template_id": "template_name",
            "name": "Test",
            "body": "Hi {{1}}",
        })


def test_normalize_template_accepts_valid_gupshup_id():
    # Gupshup ids are UUID-shaped but not strict UUIDs (contract §1.3 example has 13 chars in last group)
    result = normalize_template({
        "gupshup_template_id": "312371e9-2771-463b-8cfd-cd8994b810ccf",
        "name": "Test",
        "body": "Hi {{1}}",
    })
    assert result["gupshup_template_id"] == "312371e9-2771-463b-8cfd-cd8994b810ccf"
    assert result["variable_count"] == 1


def test_normalize_template_strips_whitespace():
    result = normalize_template({
        "gupshup_template_id": "  312371e9-2771-463b-8cfd-cd8994b810ccf  ",
        "name": "  Test  ",
        "body": "  Hi {{1}}  ",
    })
    assert result["gupshup_template_id"] == "312371e9-2771-463b-8cfd-cd8994b810ccf"
    assert result["name"] == "Test"
    assert result["body"] == "Hi {{1}}"


def test_normalize_template_builds_labels_per_slot():
    result = normalize_template({
        "gupshup_template_id": "312371e9-2771-463b-8cfd-cd8994b810ccf",
        "name": "Test",
        "body": "Hi {{1}} from {{2}}, {{3}}?",
        "variable_labels": ["Name"],  # Only one label for 3 slots
    })
    assert result["variable_labels"] == ["Name", "Variable 2", "Variable 3"]


def test_normalize_template_blank_labels_become_defaults():
    result = normalize_template({
        "gupshup_template_id": "312371e9-2771-463b-8cfd-cd8994b810ccf",
        "name": "Test",
        "body": "Hi {{1}} from {{2}}",
        "variable_labels": ["Name", ""],
    })
    assert result["variable_labels"] == ["Name", "Variable 2"]


def test_normalize_template_builds_defaults_per_slot():
    result = normalize_template({
        "gupshup_template_id": "312371e9-2771-463b-8cfd-cd8994b810ccf",
        "name": "Test",
        "body": "Hi {{1}} from {{2}}, {{3}}?",
        "variable_defaults": ["value1"],
    })
    assert result["variable_defaults"] == ["value1", None, None]


def test_normalize_template_blank_defaults_become_none():
    result = normalize_template({
        "gupshup_template_id": "312371e9-2771-463b-8cfd-cd8994b810ccf",
        "name": "Test",
        "body": "Hi {{1}} from {{2}}",
        "variable_defaults": ["value1", "  "],
    })
    assert result["variable_defaults"] == ["value1", None]


def test_normalize_template_removes_blank_buttons():
    result = normalize_template({
        "gupshup_template_id": "312371e9-2771-463b-8cfd-cd8994b810ccf",
        "name": "Test",
        "body": "Hi {{1}}",
        "buttons": ["Yes", "  ", "No"],
    })
    assert result["buttons"] == ["Yes", "No"]


def test_normalize_template_rejects_gap_in_variables():
    with pytest.raises(ValueError, match=r"\{\{2\}\}"):
        normalize_template({
            "gupshup_template_id": "312371e9-2771-463b-8cfd-cd8994b810ccf",
            "name": "Test",
            "body": "Hi {{1}}, see {{3}}",
        })


def test_variable_count_rejects_out_of_order_slots():
    # Slots must first appear in order: {{1}}, {{2}}, etc. (Gupshup fills in order of occurrence)
    with pytest.raises(ValueError, match="order"):
        variable_count("{{2}} {{1}}")
    with pytest.raises(ValueError, match="order"):
        variable_count("{{1}} {{3}} {{2}}")


def test_variable_count_allows_repeats_after_order():
    # Repeats are fine as long as first appearance is in order
    assert variable_count("{{1}} {{2}} {{1}}") == 2


def test_normalize_template_with_none_holes_in_labels():
    # None holes in labels should be filled with defaults
    result = normalize_template({
        "gupshup_template_id": "312371e9-2771-463b-8cfd-cd8994b810ccf",
        "name": "Test",
        "body": "Hi {{1}} from {{2}}, {{3}}?",
        "variable_labels": ["Name", None, "City"],
    })
    assert result["variable_labels"] == ["Name", "Variable 2", "City"]


def test_normalize_template_with_none_holes_in_defaults():
    # None holes in defaults pass through as None
    result = normalize_template({
        "gupshup_template_id": "312371e9-2771-463b-8cfd-cd8994b810ccf",
        "name": "Test",
        "body": "Hi {{1}} from {{2}}, {{3}}?",
        "variable_defaults": ["value1", None, "value3"],
    })
    assert result["variable_defaults"] == ["value1", None, "value3"]


def test_locked_changes_detects_body_change():
    current = {"body": "Old body", "gupshup_template_id": "123"}
    new = {"body": "New body", "gupshup_template_id": "123"}
    changes = locked_changes(current, new)
    assert "body" in changes


def test_locked_changes_detects_gupshup_id_change():
    current = {"body": "Hi", "gupshup_template_id": "id1"}
    new = {"body": "Hi", "gupshup_template_id": "id2"}
    changes = locked_changes(current, new)
    assert "gupshup_template_id" in changes


def test_locked_changes_ignores_whitespace_in_id():
    current = {"body": "Hi", "gupshup_template_id": "  id1  "}
    new = {"body": "Hi", "gupshup_template_id": "id1"}
    changes = locked_changes(current, new)
    assert "gupshup_template_id" not in changes


def test_locked_changes_empty_when_no_locked_change():
    current = {"body": "Hi", "gupshup_template_id": "123"}
    new = {"body": "Hi", "gupshup_template_id": "123", "name": "NewName"}
    changes = locked_changes(current, new)
    assert len(changes) == 0


def test_locked_changes_allows_other_field_changes():
    current = {"body": "Hi", "gupshup_template_id": "123", "active": True}
    new = {"body": "Hi", "gupshup_template_id": "123", "active": False}
    changes = locked_changes(current, new)
    assert "active" not in changes
