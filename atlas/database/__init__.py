from atlas.database.engine import DATABASE_PATH, engine as default_engine
from atlas.database.models import Base


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


__all__ = [
    "initialize_database",
]
