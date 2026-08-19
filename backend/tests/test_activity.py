"""The activity log — what changed, not which URL was hit.

Replaces audit_logs, which recorded HTTP requests: method, path, status. That told you
POST /v1/leads/{id}/confirm returned 200 and nothing else — not which lead, not what
changed, not from what to what. It was also written from middleware after the
response, so it could log a success whose transaction had rolled back.

Everything here writes through the caller's own connection, so the log row commits or
rolls back with the change it describes and the two can never drift.
"""

from app.services.activity import Actor, changes_between, humanize, row_for

ACTOR = Actor(email="rm@openhouse.in", name="Asha", role="rm")


def test_a_row_carries_the_change_not_the_request():
    r = row_for(ACTOR, entity_type="lead", entity_id="L1", action="stage_change",
                field="stage", before="new", after="qualified")

    assert r["entity_type"] == "lead" and r["entity_id"] == "L1"
    assert r["action"] == "stage_change"
    assert (r["field"], r["before_value"], r["after_value"]) == ("stage", "new", "qualified")
    assert r["actor_email"] == "rm@openhouse.in"


def test_the_actor_is_denormalised_onto_the_row():
    """Name and role are copied, not joined. A user can be renamed, demoted or deleted,
    and the log has to keep saying who did it AT THE TIME."""
    r = row_for(ACTOR, entity_type="lead", entity_id="L1", action="note_added")

    assert r["actor_name"] == "Asha"
    assert r["actor_role"] == "rm"


def test_a_background_job_is_a_valid_actor():
    """Syncs and the dialer act with nobody signed in. A null actor must be
    representable, or those events simply wouldn't be logged."""
    r = row_for(None, entity_type="sync", entity_id="leads_sheet", action="sync_run")

    assert r["actor_email"] is None
    assert r["entity_type"] == "sync"


def test_values_are_stringified_so_any_type_can_be_logged():
    """before/after are TEXT: a stage is a string, miss_count an int, is_hot a bool,
    follow_up_at a datetime. Storing them typed would need a column per type."""
    r = row_for(ACTOR, entity_type="lead", entity_id="L1", action="update",
                field="miss_count", before=2, after=3)
    assert (r["before_value"], r["after_value"]) == ("2", "3")

    r = row_for(ACTOR, entity_type="lead", entity_id="L1", action="update",
                field="is_hot", before=False, after=True)
    assert (r["before_value"], r["after_value"]) == ("false", "true")


def test_none_stays_none_rather_than_the_string_none():
    """"None" as a value would read as a real prior value in the UI."""
    r = row_for(ACTOR, entity_type="lead", entity_id="L1", action="update",
                field="assigned_to", before=None, after="Asha")
    assert r["before_value"] is None and r["after_value"] == "Asha"


# --- diffing ----------------------------------------------------------------

def test_only_changed_fields_produce_rows():
    """An edit form posts every field. Logging all of them would bury the one that
    actually changed."""
    rows = changes_between(ACTOR, "lead", "L1",
                           before={"stage": "new", "city": "Noida", "society": "Gaur"},
                           after={"stage": "qualified", "city": "Noida", "society": "Gaur"})

    assert len(rows) == 1
    assert rows[0]["field"] == "stage"
    assert rows[0]["after_value"] == "qualified"


def test_a_stage_change_is_its_own_action_not_a_generic_update():
    """Stage is the spine of this app — every page is an equality on it. The Logs page
    filters on action, so folding stage into 'update' would make the single most
    interesting event unfilterable."""
    rows = changes_between(ACTOR, "lead", "L1",
                           before={"stage": "new"}, after={"stage": "qualified"})
    assert rows[0]["action"] == "stage_change"

    rows = changes_between(ACTOR, "lead", "L1",
                           before={"city": "Noida"}, after={"city": "Gurgaon"})
    assert rows[0]["action"] == "update"


def test_nothing_changed_means_nothing_logged():
    """A save that changes nothing is not an event."""
    assert changes_between(ACTOR, "lead", "L1", before={"stage": "new"},
                           after={"stage": "new"}) == []


def test_a_field_absent_from_the_update_is_not_treated_as_cleared():
    """PATCH sends only what it touches. Treating a missing key as null would log every
    untouched column as having been wiped."""
    assert changes_between(ACTOR, "lead", "L1",
                           before={"stage": "new", "city": "Noida"},
                           after={"stage": "new"}) == []


# --- humanising ---------------------------------------------------------------

def test_ids_are_humanised_but_the_raw_id_is_kept():
    """A log reading 'assigned_to: 3f2a… → 9c81…' is unreadable. The doc's rule: show
    the name, keep the id in metadata so the entry stays traceable."""
    r = humanize(row_for(ACTOR, entity_type="lead", entity_id="L1", action="update",
                         field="assigned_to", before="id-1", after="id-2"),
                 names={"id-1": "Asha", "id-2": "Vikram"})

    assert (r["before_value"], r["after_value"]) == ("Asha", "Vikram")
    assert r["metadata"]["before_id"] == "id-1"
    assert r["metadata"]["after_id"] == "id-2"


def test_an_unknown_id_is_left_alone_rather_than_blanked():
    r = humanize(row_for(ACTOR, entity_type="lead", entity_id="L1", action="update",
                         field="assigned_to", before="id-9", after=None),
                 names={})
    assert r["before_value"] == "id-9"
