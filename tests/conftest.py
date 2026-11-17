import atlas.alerts as alerts_module
import pytest
from sqlalchemy import create_engine

import atlas.devices.store as devices_store_module
import atlas.knowledge.queries as queries_module
import atlas.knowledge.store as store_module
import atlas.monitoring.uptime as uptime_module
import atlas.posture.store as posture_store_module
import atlas.wiring.store as wiring_store_module
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
    monkeypatch.setattr(devices_store_module, "engine", engine)
    monkeypatch.setattr(posture_store_module, "engine", engine)
    monkeypatch.setattr(wiring_store_module, "engine", engine)
    monkeypatch.setattr(alerts_module, "engine", engine)
    monkeypatch.setattr(uptime_module, "engine", engine)

    yield engine

    engine.dispose()


@pytest.fixture(autouse=True)
def no_network_lookups(monkeypatch):
    """Tests never ask the real LAN (mDNS / UPnP), never download the MAC maker list and never resolve a download
    server's name; the tests for those pieces call them with fakes."""

    from atlas.devices import discover, identify
    from atlas.posture.collectors import asn

    def offline(*args, **kwargs):
        raise OSError("tests are offline")

    monkeypatch.setattr(discover, "mdns", lambda timeout=2.5: {})
    monkeypatch.setattr(discover, "ssdp", lambda timeout=2.5, fetch=None: {})
    monkeypatch.setattr(identify, "GET", offline)
    monkeypatch.setattr(asn, "RESOLVE", offline)
