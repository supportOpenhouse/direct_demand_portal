"""The test_rm role.

A calling RM used for dry runs: dialled by campaigns like anyone else, tagged TEST in
the picker so an admin can see what they're aiming at, and never handed a WhatsApp
conversation.

Every other restriction must apply to it exactly as it does to `rm`. That's the part
worth testing: the restriction sites are all written `role == "rm"`, so a role that
isn't matched there doesn't get "no restriction that mentions it" — it falls through
to the ADMIN branch and sees everything. A new calling role is one missed predicate
away from handing a test account the whole lead table.
"""
import re

from app.core.auth import CALLING_ROLES, is_calling_rm


def _sql(stmt) -> str:
    """Statement text with `--` comments stripped — these assertions are about what
    the SQL does, and prose explaining a rule mentions the very words it excludes."""
    body = re.sub(r"--[^\n]*", "", str(stmt))
    return re.sub(r"\s+", " ", body).strip()


def test_test_rm_is_a_calling_role():
    assert is_calling_rm("test_rm")
    assert is_calling_rm("rm")
    assert "test_rm" in CALLING_ROLES and "rm" in CALLING_ROLES


def test_admin_is_not_a_calling_role():
    """Campaigns ring handsets — an admin must not land in a dial pool by accident."""
    assert not is_calling_rm("admin")
    assert not is_calling_rm(None)
    assert not is_calling_rm("")


def test_test_rm_sees_only_its_own_leads():
    """The whole risk in one test. _role_scope's else-branch is 'true' — every lead in
    the system — so a calling role that slips past the check is a data leak, not a
    missing feature."""
    from app.routers.leads import _role_scope

    clause, params = _role_scope({"role": "test_rm", "name": "Tester", "email": "t@x.in"})

    assert clause != "true"
    assert "lower(assigned_to) = ANY(:aliases)" in clause
    assert params["aliases"]


def test_test_rm_with_no_resolvable_name_sees_nothing():
    """Same fail-closed behaviour rm has: no aliases means no rows, not all rows."""
    from app.routers.leads import _role_scope

    assert _role_scope({"role": "test_rm"})[0] == "false"


def test_test_rm_whatsapp_threads_are_scoped_like_an_rms():
    """_thread_scope returns None for 'unrestricted'. A calling role must never get it."""
    from app.routers.gupshup import _thread_scope

    assert _thread_scope({"role": "test_rm", "name": "Tester"}) is not None
    assert _thread_scope({"role": "admin"}) is None


def test_the_dial_pool_includes_test_rm():
    """A test RM exists to be dialled — excluding them from the picker defeats the
    point of the role."""
    from app.routers import dialer

    src = _sql(dialer._CALLABLE_RMS)
    assert "role IN ('rm', 'test_rm')" in src or "role = ANY" in src
    assert "active" in src


def test_whatsapp_assignment_never_picks_a_test_rm():
    """The one thing test_rm must NOT get. wa_assign hands real customer conversations
    to whoever it picks; a test account answering a real buyer is worse than an
    unassigned thread."""
    from app.services import wa_assign

    src = _sql(wa_assign._LEAST_LOADED)
    assert "u.role = 'rm'" in src, "must stay the exact role, not a calling-role set"
    assert "test_rm" not in src


def test_test_rm_is_an_assignable_role():
    from app.routers.users import ROLES

    assert ROLES == {"admin", "rm", "test_rm"}
