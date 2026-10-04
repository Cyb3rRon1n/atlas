from sqlalchemy import inspect, text

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


def _migrate_devices_table(engine):

    existing = {column["name"] for column in inspect(engine).get_columns("devices")}

    with engine.begin() as connection:

        for column, definition in DEVICE_COLUMN_MIGRATIONS.items():

            if column not in existing:
                connection.execute(text(f"ALTER TABLE devices ADD COLUMN {column} {definition}"))


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

    _migrate_devices_table(engine)


__all__ = [
    "initialize_database",
]
