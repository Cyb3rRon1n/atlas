from pathlib import Path

from sqlalchemy import create_engine


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
