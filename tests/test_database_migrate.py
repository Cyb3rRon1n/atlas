from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

import lanxang.database as database_module
from lanxang.database import initialize_database


def test_initialize_database_adds_missing_device_columns(tmp_path):
    """
    A devices table from before connection/uplink_id existed gets both
    columns added in place via ALTER TABLE (create_all never touches an
    existing table's columns). Running it twice must not error, and an
    existing row reads back the new columns' defaults.
    """

    engine = create_engine(f"sqlite:///{tmp_path / 'migrate.db'}")

    with engine.begin() as connection:

        connection.execute(text("""
            CREATE TABLE devices (
                id INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL,
                kind VARCHAR NOT NULL DEFAULT 'other',
                tags VARCHAR NOT NULL DEFAULT '[]',
                notes VARCHAR NOT NULL DEFAULT '',
                important BOOLEAN NOT NULL DEFAULT 0,
                state VARCHAR NOT NULL DEFAULT 'new',
                locked_fields VARCHAR NOT NULL DEFAULT '[]',
                suggested_merge_id INTEGER,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """))

        connection.execute(text(
            "INSERT INTO devices (name, created_at, updated_at) VALUES ('old', '2026-01-01', '2026-01-01')"
        ))

    initialize_database(engine)
    initialize_database(engine)  # second run must not error

    columns = {column["name"] for column in inspect(engine).get_columns("devices")}
    assert {"connection", "uplink_id"} <= columns

    with engine.connect() as connection:
        row = connection.execute(text("SELECT connection, uplink_id FROM devices WHERE name = 'old'")).one()

    assert row.connection == "unknown"
    assert row.uplink_id is None


def test_migrate_devices_table_tolerates_a_concurrent_migration(tmp_path, monkeypatch):
    """
    atlas-web and atlas-scan share the same SQLite file and can both call
    initialize_database() at the same moment. Both would read `existing`
    before either ALTERs, so the loser's ALTER hits sqlite3's own "duplicate
    column name" error - that has to be treated as "already migrated, fine",
    not crash the loser's startup.
    """

    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}")

    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE devices (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
        ))

    database_module._migrate_table(engine, "devices", database_module.DEVICE_COLUMN_MIGRATIONS)  # the "winner" adds both columns

    class StaleInspector:
        """Stands in for a second process that read the column list before
        the winner's ALTER had landed - it still thinks both columns are missing."""

        def get_columns(self, table_name):
            return []

    monkeypatch.setattr(database_module, "inspect", lambda target_engine: StaleInspector())

    database_module._migrate_table(engine, "devices", database_module.DEVICE_COLUMN_MIGRATIONS)  # the "loser" - must not raise

    columns = {column["name"] for column in inspect(engine).get_columns("devices")}
    assert {"connection", "uplink_id"} <= columns



def _statements(engine):

    from sqlalchemy import event

    seen = []
    event.listen(engine, "before_cursor_execute", lambda conn, cur, statement, *rest: seen.append(statement))
    return seen


def test_initialize_database_renames_lanxang_event_types_back(tmp_path, monkeypatch):
    """Images built from main before 1.0 wrote lanxang.* event types; the stored names stay atlas.*."""

    monkeypatch.setattr(database_module, "_HEALED", set())
    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    initialize_database(engine)
    monkeypatch.setattr(database_module, "_HEALED", set())

    with engine.begin() as connection:
        for kind in ("lanxang.proxmox.scan.completed", "atlas.monitor.completed"):
            connection.execute(text("INSERT INTO events (event_type, source, payload, created_at) "
                                    "VALUES (:kind, 'test', '{}', '2026-11-01')"), {"kind": kind})

    seen = _statements(engine)
    initialize_database(engine)
    monkeypatch.setattr(database_module, "_HEALED", set())
    initialize_database(engine)  # second run is harmless

    with engine.connect() as connection:
        kinds = sorted(connection.execute(text("SELECT event_type FROM events")).scalars())

    assert kinds == ["atlas.monitor.completed", "atlas.proxmox.scan.completed"]
    assert sum(s.startswith("UPDATE events") for s in seen) == 1      # the second run found nothing to heal


def test_event_heal_never_writes_when_nothing_matches_and_runs_once(tmp_path, monkeypatch):
    """The check is an index read: no UPDATE (no write lock) without lanxang.* rows, and once per process."""

    monkeypatch.setattr(database_module, "_HEALED", set())
    engine = create_engine(f"sqlite:///{tmp_path / 'quiet.db'}")
    seen = _statements(engine)
    initialize_database(engine)
    initialize_database(engine)

    assert not any(s.startswith("UPDATE events") for s in seen)
    assert sum("FROM events WHERE event_type >=" in s for s in seen) == 1

    # a writer holding the lock does not block the next store read
    import sqlite3
    writer = sqlite3.connect(tmp_path / "quiet.db", timeout=0)
    writer.execute("BEGIN IMMEDIATE")
    try:
        busy = create_engine(f"sqlite:///{tmp_path / 'quiet.db'}", connect_args={"timeout": 0})
        monkeypatch.setattr(database_module, "_HEALED", set())
        initialize_database(busy)
    finally:
        writer.rollback()
        writer.close()


def test_initialize_database_tolerates_a_concurrent_create_all(tmp_path, monkeypatch):
    """
    On a fresh data volume the web and scan containers both call
    initialize_database() at once; create_all() is check-then-create, so the
    loser's CREATE TABLE can hit "table events already exists". That means
    the other process made it - initialization has to retry, not crash.
    """

    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    real_create_all = database_module.Base.metadata.create_all
    calls = []

    def racing_create_all(bind, *args, **kwargs):

        calls.append(1)

        if len(calls) == 1:
            real_create_all(bind)     # the "winner" gets there first

        if len(calls) <= 2:           # and is still creating tables when the retry runs
            raise OperationalError("CREATE TABLE events (...)", {}, Exception("table events already exists"))

        return real_create_all(bind, *args, **kwargs)

    monkeypatch.setattr(database_module.Base.metadata, "create_all", racing_create_all)

    initialize_database(engine)

    assert len(calls) == 3
    assert "events" in inspect(engine).get_table_names()

    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM events")).scalar() == 0
