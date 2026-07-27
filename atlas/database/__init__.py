from atlas.database.engine import DATABASE_PATH, engine as default_engine
from atlas.database.models import Base


def initialize_database(engine=None):
    """
    Create any tables missing from the target database. Safe to call
    repeatedly - SQLAlchemy only creates tables that don't already exist.
    """

    if engine is None:

        DATABASE_PATH.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        engine = default_engine

    Base.metadata.create_all(
        engine
    )


__all__ = [
    "initialize_database",
]
