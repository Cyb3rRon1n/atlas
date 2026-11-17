from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from atlas.database.engine import DATABASE_PATH, engine as default_engine
from atlas.database.models import Base


# create_all() only creates tables that don't exist yet - it never alters an
# existing table's columns. A column added to a model after devices already
# shipped (connection, uplink_id) needs an explicit ALTER for every database
# that predates it; keyed by column name so a second run is a no-op.
DEVICE_COLUMN_MIGRATIONS = {
    "connection": "VARCHAR NOT NULL DEFAULT 'unknown'",
    "uplink_id": "INTEGER REFERENCES devices(id)",
}
ALERT_COLUMN_MIGRATIONS = {
    "acked_at": "DATETIME",
}


def _migrate_table(engine, table, migrations):

    existing = {column["name"] for column in inspect(engine).get_columns(table)}

    with engine.begin() as connection:

        for column, definition in migrations.items():

            if column in existing:
                continue

            try:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))

            except OperationalError as error:

                # atlas-web and atlas-scan share this database and can both
                # start the migration at once; both read `existing` before
                # either ALTERs, so the loser hits exactly this error, which
                # means the column is already there - not a real failure.
                if "duplicate column name" not in str(error).lower():
                    raise


def initialize_database(engine=None):
    """
    Create any tables missing from the target database. Safe to call
    repeatedly - SQLAlchemy only creates tables that don't already exist.

    Every real call site (KnowledgeStore/KnowledgeQueries) passes its own
    module-bound `engine` explicitly rather than relying on the default
    argument, and that bound name is the same object as `default_engine`
    unless a test has monkeypatched it - so the directory-creation check
    has to compare identity against `default_engine`, not against `None`,
    or it would never fire in real usage.
    """

    if engine is None:
        engine = default_engine

    if engine is default_engine:

        DATABASE_PATH.parent.mkdir(
            parents=True,
            exist_ok=True
        )

    Base.metadata.create_all(
        engine
    )

    _migrate_table(engine, "devices", DEVICE_COLUMN_MIGRATIONS)
    _migrate_table(engine, "alerts", ALERT_COLUMN_MIGRATIONS)

    # Indexes for tables that existed before them (create_all only indexes new tables): the newest event of a
    # type (Home, Overview) and the trimming of old rows would otherwise read the whole table.
    with engine.begin() as connection:
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_events_type_time ON events (event_type, created_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_events_time ON events (created_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_environment_time ON environment (created_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_uptime_name_time ON uptime (name, checked_at)"))


__all__ = [
    "initialize_database",
]
