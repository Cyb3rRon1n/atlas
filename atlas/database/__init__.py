from atlas.database.engine import engine
from atlas.database.models import Base


def initialize_database():

    Base.metadata.create_all(
        engine
    )


__all__ = [
    "initialize_database",
]
