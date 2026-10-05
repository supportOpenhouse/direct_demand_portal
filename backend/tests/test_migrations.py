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


def test_the_campaign_indexes_run_after_the_columns_they_need_in_their_own_transaction():
    """G-6 / D-M9. ix_wa_messages_whatsapp_id needs the whatsapp_id column that the schema transaction adds. Run
    INSIDE that transaction, a failing CREATE INDEX would roll back every ADD COLUMN; run before it, on a database
    that lacks the column, it fails. So: its own transaction, after the schema one."""
    import inspect

    from app import migrations
    assert ("wa_messages", "whatsapp_id", "TEXT") in _ADD_COLUMNS
    assert migrations._CAMPAIGN_INDEXES == (
        "CREATE INDEX IF NOT EXISTS ix_wa_messages_whatsapp_id ON wa_messages (whatsapp_id)",
        "CREATE INDEX IF NOT EXISTS ix_wa_messages_in_phone10 ON wa_messages (right(phone, 10), created_at)"
        " WHERE direction = 'in'",
    )
    src = inspect.getsource(migrations.run_migrations)
    schema, rest = src.split('log.exception("schema (ADD COLUMN) migrations failed")', 1)
    assert "_CAMPAIGN_INDEXES" not in schema, "not inside the shared ADD COLUMN transaction"
    idx = rest.split('log.exception("campaign index migrations failed")', 1)[0]
    assert "async with engine.begin() as conn:" in idx and "for stmt in _CAMPAIGN_INDEXES:" in idx


async def test_run_migrations_commits_the_columns_before_creating_the_indexes():
    """The order, run: every ADD COLUMN commits; then the two indexes in a transaction of their own."""
    from app import migrations

    events = []

    class _Conn:
        async def execute(self, stmt, params=None):
            events.append(str(stmt).strip().split("\n")[0][:60])

            class _R:
                def mappings(self):
                    return []

                def __iter__(self):
                    return iter([])
            return _R()

    class _Ctx:
        async def __aenter__(self):
            events.append("BEGIN")
            return _Conn()

        async def __aexit__(self, *a):
            events.append("COMMIT")
            return False

    class _Eng:
        def begin(self):
            return _Ctx()
    await migrations.run_migrations(_Eng())
    first_commit = events.index("COMMIT")
    wa_id_col = next(i for i, e in enumerate(events) if "ADD COLUMN IF NOT EXISTS whatsapp_id" in e)
    ix = next(i for i, e in enumerate(events) if "ix_wa_messages_whatsapp_id" in e)
    assert wa_id_col < first_commit < ix
    assert events[ix - 1] == "BEGIN" and events[ix + 1].startswith("CREATE INDEX IF NOT EXISTS ix_wa_messages_in_phone10")
    assert events[ix + 2] == "COMMIT"
