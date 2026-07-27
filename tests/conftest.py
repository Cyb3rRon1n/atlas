import pytest
from sqlalchemy import create_engine

import atlas.knowledge.queries as queries_module
import atlas.knowledge.store as store_module
from atlas.database.models import Base


@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    """
    Run a test from an empty temp directory so it never reads the
    developer's real atlas.yaml or writes into the real repo.
    """

    monkeypatch.chdir(tmp_path)

    return tmp_path


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """
    Point KnowledgeStore/KnowledgeQueries at a throwaway SQLite file
    instead of the committed inventory/atlas.db.

    store.py and queries.py each did `from atlas.database.engine import
    engine`, binding the name locally - patching
    atlas.database.engine.engine would not affect those already-bound
    references, so the importing modules' attributes are patched
    directly instead.
    """

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test-atlas.db'}"
    )

    Base.metadata.create_all(engine)

    monkeypatch.setattr(store_module, "engine", engine)
    monkeypatch.setattr(queries_module, "engine", engine)

    yield engine

    engine.dispose()
