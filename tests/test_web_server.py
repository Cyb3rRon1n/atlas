import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from atlas.intelligence.context import AtlasEnvironmentContext
from atlas.knowledge.store import KnowledgeStore
from atlas.web.server import AtlasWebHandler


@pytest.fixture
def running_server(temp_db):
    """
    A real server on an OS-assigned ephemeral port (host "127.0.0.1",
    port 0) in a background thread - a real HTTP round trip against a
    real socket, not a mocked request object, the same "verify for
    real, not just against mocks" standard this project applies to its
    other integrations. Entirely hermetic: no external system, no real
    infrastructure dependency, just this process talking to itself.
    """

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), AtlasWebHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()


def _get(url):

    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def test_overview_route_with_no_data(running_server):

    status, body = _get(running_server + "/")

    assert status == 200
    assert "No inventory found" in body


def test_overview_route_with_real_saved_environment(running_server):

    store = KnowledgeStore()
    environment = AtlasEnvironmentContext()
    environment.ingest_discovery({"system": {"hostname": "sentinel"}})
    store.save_environment(environment)

    status, body = _get(running_server + "/")

    assert status == 200
    assert "sentinel" in body


def test_history_route_with_no_data(running_server):

    status, body = _get(running_server + "/history")

    assert status == 200
    assert "No historical events found" in body


def test_trends_route_with_no_data(running_server):

    status, body = _get(running_server + "/trends")

    assert status == 200
    assert "No monitoring history found" in body


def test_unknown_route_returns_404(running_server):

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(running_server + "/nope")

    assert exc_info.value.code == 404


def test_only_get_routes_exist_no_write_path():
    """
    A structural guard, not just a behavioral one: confirms this
    handler defines no do_POST/do_PUT/do_DELETE at all, so a write
    path can't be silently added to this class without this test
    naming it - matches this feature's own "no new write path" scope.
    """

    for verb in ("do_POST", "do_PUT", "do_DELETE", "do_PATCH"):
        assert not hasattr(AtlasWebHandler, verb)
