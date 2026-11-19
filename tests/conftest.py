import lanxang.alerts as alerts_module
import pytest
from sqlalchemy import create_engine

import lanxang.devices.store as devices_store_module
import lanxang.knowledge.queries as queries_module
import lanxang.knowledge.store as store_module
import lanxang.monitoring.uptime as uptime_module
import lanxang.posture.store as posture_store_module
import lanxang.wiring.store as wiring_store_module
from lanxang.database.models import Base


@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    """
    Run a test from an empty temp directory so it never reads the
    developer's real lanxang.yaml or writes into the real repo.
    """

    monkeypatch.chdir(tmp_path)

    return tmp_path


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """
    Point KnowledgeStore/KnowledgeQueries at a throwaway SQLite file
    instead of the committed inventory/atlas.db.

    store.py and queries.py each did `from lanxang.database.engine import
    engine`, binding the name locally - patching
    lanxang.database.engine.engine would not affect those already-bound
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
def chat_flag_reset(monkeypatch):
    """The web server sets lanxang.web.render.AI_ON per request; put it back so one test's server can't hide the
    chat from the next test's pages."""

    from lanxang.web import render
    monkeypatch.setattr(render, "AI_ON", True)
    monkeypatch.setattr(render, "DISPLAY", None)


@pytest.fixture(autouse=True)
def no_network_lookups(monkeypatch):
    """Tests never ask the real LAN (mDNS / UPnP), never download the MAC maker list and never resolve a download
    server's name; the tests for those pieces call them with fakes."""

    from lanxang.devices import discover, identify
    from lanxang.posture.collectors import asn

    def offline(*args, **kwargs):
        raise OSError("tests are offline")

    monkeypatch.setattr(discover, "mdns", lambda timeout=2.5: {})
    monkeypatch.setattr(discover, "ssdp", lambda timeout=2.5, fetch=None: {})
    monkeypatch.setattr(identify, "GET", offline)
    monkeypatch.setattr(asn, "RESOLVE", offline)
    from lanxang.monitoring import internet
    monkeypatch.setattr(internet, "_connect", lambda host, port, timeout: (5.0, False))
    monkeypatch.setattr(internet, "_gateway", lambda: None)
    monkeypatch.setattr(internet, "_ask", lambda server, name, timeout: 5.0)
    monkeypatch.setattr(internet, "_system", lambda name, timeout: 5.0)
