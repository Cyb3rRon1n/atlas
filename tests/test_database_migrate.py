from sqlalchemy import create_engine, inspect, text

import atlas.database as database_module
from atlas.database import initialize_database


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

    database_module._migrate_devices_table(engine)  # the "winner" adds both columns

    class StaleInspector:
        """Stands in for a second process that read the column list before
        the winner's ALTER had landed - it still thinks both columns are missing."""

        def get_columns(self, table_name):
            return []

    monkeypatch.setattr(database_module, "inspect", lambda target_engine: StaleInspector())

    database_module._migrate_devices_table(engine)  # the "loser" - must not raise

    columns = {column["name"] for column in inspect(engine).get_columns("devices")}
    assert {"connection", "uplink_id"} <= columns
