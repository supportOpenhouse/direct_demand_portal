"""Schema migrations.

Every ALTER runs inside ONE transaction (see the comment in migrations.py on why
schema changes are separated from the back-fills). That makes a typo expensive: a
bad table name doesn't skip its own statement, it fails the transaction and takes
every ADD COLUMN with it — and `run_migrations` swallows the exception, so the only
symptom is a freshly-deployed app 500ing on a column that never got added.

These assert the lists against the models rather than against a live database.
"""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.migrations import _ADD_COLUMNS, _ID_DEFAULT_TABLES
from app.models import Base


def test_every_id_default_table_actually_exists():
    """A typo here fails the whole schema transaction, silently."""
    unknown = [t for t in _ID_DEFAULT_TABLES if t not in Base.metadata.tables]
    assert not unknown, f"not real tables: {unknown}"


def test_every_id_default_table_has_a_uuid_column_called_id():
    """`ALTER COLUMN id` is written literally, so a table whose key is named something
    else (lead_confirmed_data.lead_id) would raise rather than be skipped."""
    for name in _ID_DEFAULT_TABLES:
        col = Base.metadata.tables[name].columns.get("id")
        assert col is not None, f"{name} has no `id` column"
        assert isinstance(col.type, UUID), f"{name}.id is {col.type}, not UUID"


def test_a_foreign_key_never_gets_a_generated_default():
    """lead_confirmed_data.lead_id is a uuid primary key too, but it POINTS AT
    leads.id. Defaulting it would mint a reference to a lead that doesn't exist."""
    assert "lead_confirmed_data" not in _ID_DEFAULT_TABLES


def test_the_orm_still_supplies_its_own_id():
    """The db default is a safety net for raw inserts, not a replacement. If the
    client-side default were dropped, _cols_per_row's bind-parameter count — and the
    chunking that keeps inserts under Postgres' 32767 cap — would both shift.

    Asserts the property, not the mechanism: SQLAlchemy wraps a bare callable, so
    `default.arg is uuid.uuid4` is false even when nothing has changed."""
    default = Base.metadata.tables["leads"].columns["id"].default
    assert default.is_callable
    assert isinstance(default.arg(None), uuid.UUID)


def test_added_columns_name_real_tables_too():
    """Same transaction, same failure mode."""
    unknown = sorted({t for t, _, _ in _ADD_COLUMNS if t not in Base.metadata.tables})
    assert not unknown, f"not real tables: {unknown}"


def test_added_columns_name_real_columns_too():
    """The table check above passes for a column the ORM has never heard of.

    That gap is real: `leads.meta_lead_id` was added to _ADD_COLUMNS and to the
    database while the model still didn't declare it, and every test stayed green.
    A column Postgres has and the ORM doesn't is invisible to every query built from
    the model — which reads as data loss, not as a schema error.
    """
    missing = sorted(
        f"{table}.{col}"
        for table, col, _ in _ADD_COLUMNS
        if col not in Base.metadata.tables[table].columns
    )
    assert not missing, f"in _ADD_COLUMNS but not on the model: {missing}"
