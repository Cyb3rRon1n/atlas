from pathlib import Path

from sqlalchemy import create_engine, event


DATABASE_PATH = Path(
    "inventory/atlas.db"
)


DATABASE_URL = (
    f"sqlite:///{DATABASE_PATH}"
)


engine = create_engine(
    DATABASE_URL,
    echo=False
)


def enable_wal(target_engine):
    """
    WAL + a 5s busy timeout on every new connection: the atlas web container
    and the atlas-scan container write the same SQLite file, and the default
    rollback journal would make one of them fail with "database is locked".
    """

    @event.listens_for(target_engine, "connect")
    def _pragmas(dbapi_connection, _record):

        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


enable_wal(engine)
