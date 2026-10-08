import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from atlas.intelligence.context import AtlasEnvironmentContext
from atlas.knowledge.store import KnowledgeStore
from atlas.web.server import AtlasWebHandler, same_origin


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


def _get_allow_error(url):

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        with error:
            return error.code, error.read().decode("utf-8")


def test_posture_route_at_root(running_server):

    status, body = _get(running_server + "/")

    assert status == 200
    assert 'id="posture-map"' in body


def test_overview_route_with_no_data(running_server):

    status, body = _get(running_server + "/overview")

    assert status == 200
    assert "No inventory found" in body


def test_overview_route_with_real_saved_environment(running_server):

    store = KnowledgeStore()
    environment = AtlasEnvironmentContext()
    environment.ingest_discovery({"system": {"hostname": "sentinel"}})
    store.save_environment(environment)

    status, body = _get(running_server + "/overview")

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


def _post(url, body, origin=None, raw=None):

    headers = {"Content-Type": "application/json"}

    if origin:
        headers["Origin"] = origin

    data = raw if raw is not None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())

    except urllib.error.HTTPError as error:
        with error:
            return error.code, json.loads(error.read() or b"null")


def _seed_device():

    from atlas.devices import Sighting
    from atlas.devices.store import InventoryStore

    store = InventoryStore()
    # A globally-assigned-looking MAC (locally-administered bit unset) - atlas.devices.wiring
    # guesses "wireless" from that bit, and this device needs to default to visible/wired.
    store.record_run("lan", [Sighting("lan", "00:01", ip="192.168.10.1", mac="00:01", hostname="router")])

    return store, store.devices()[0]["id"]


def test_post_requires_same_origin(running_server):

    store, device_id = _seed_device()
    url = f"{running_server}/api/devices/{device_id}"

    assert _post(url, {"name": "x"})[0] == 403
    assert _post(url, {"name": "x"}, origin="https://evil.example")[0] == 403
    assert store.device(device_id)["name"] == "router"

    assert _post(url, {"name": "UniFi"}, origin=running_server) == (200, {"ok": True})
    assert store.device(device_id)["name"] == "UniFi"


def test_post_rejects_bad_json_big_bodies_and_unknown_paths(running_server):

    store, device_id = _seed_device()
    url = f"{running_server}/api/devices/{device_id}"

    assert _post(url, None, origin=running_server, raw=b"{nope")[0] == 400
    assert _post(f"{running_server}/api/whatever", {}, origin=running_server)[0] == 404

    # Oversized: send only the headers - the server must refuse on Content-Length alone,
    # without reading (a real body would race the early 413 and reset the connection).
    import http.client
    from urllib.parse import urlsplit
    connection = http.client.HTTPConnection(urlsplit(running_server).netloc, timeout=5)
    connection.putrequest("POST", f"/api/devices/{device_id}")
    connection.putheader("Origin", running_server)
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", "70000")
    connection.endheaders()
    assert connection.getresponse().status == 413
    connection.close()


def test_chat_page_and_device_prefill(running_server):

    _, device_id = _seed_device()

    status, body = _get(running_server + "/chat")
    assert status == 200 and 'id="ask"' in body

    status, body = _get(running_server + f"/chat?device={device_id}")
    assert status == 200 and "Tell me about router" in body


def test_chat_prefill_falls_back_to_ip_then_id_when_name_is_none(running_server, monkeypatch):
    """
    device['name'] is normally always set, but the prefill must not assume
    that: a nameless device used to render "Tell me about None".
    """

    from atlas.devices.store import InventoryStore

    nameless = {"id": 9, "name": None, "ip": "10.0.0.5", "status": "online", "state": "known",
                "sightings": [{"source": "lan"}]}

    monkeypatch.setattr(InventoryStore, "device", lambda self, device_id: nameless)

    status, body = _get(running_server + "/chat?device=9")

    assert status == 200
    assert "Tell me about 10.0.0.5" in body
    assert "Tell me about None" not in body


def test_api_get_and_summary_counts(running_server):

    _seed_device()

    status, body = _get(running_server + "/api/devices")
    assert status == 200 and json.loads(body)[0]["name"] == "router"

    summary = json.loads(_get(running_server + "/api/summary")[1])
    assert summary["to_triage"] == 1 and summary["devices_quiet"] == 0


def test_graph_route_with_ignored_flag(running_server):

    store, device_id = _seed_device()
    store.set_fields(device_id, {"state": "ignored"})
    node_id = f"d{device_id}"

    status, body = _get(running_server + "/api/graph?ignored=1")
    graph = json.loads(body)

    assert status == 200
    assert node_id in {node["data"]["id"] for node in graph["nodes"]}


@pytest.mark.parametrize("headers, expected", [
    ({"Sec-Fetch-Site": "same-origin"}, True),
    ({"Sec-Fetch-Site": "same-site"}, False),
    ({"Origin": "http://127.0.0.1:8420", "Host": "127.0.0.1:8420"}, True),
    ({"Origin": "null", "Host": "127.0.0.1:8420"}, False),
    ({"Referer": "http://127.0.0.1:8420/devices/1", "Host": "127.0.0.1:8420"}, True),
    ({"Origin": "https://atlas.x@evil.com", "Host": "atlas.x"}, False),
    ({}, False),
], ids=[
    "sec-fetch-site same-origin passes",
    "sec-fetch-site same-site with no origin fails",
    "origin matches host passes",
    "origin null fails",
    "referer fallback matches passes",
    "userinfo trick fails",
    "nothing at all fails",
])
def test_same_origin(headers, expected):

    assert same_origin(headers) is expected


def test_post_with_non_integer_content_length_returns_400(running_server):

    import http.client
    from urllib.parse import urlsplit

    _, device_id = _seed_device()

    connection = http.client.HTTPConnection(urlsplit(running_server).netloc, timeout=5)
    connection.putrequest("POST", f"/api/devices/{device_id}")
    connection.putheader("Origin", running_server)
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", "not-a-number")
    connection.endheaders()
    assert connection.getresponse().status == 400
    connection.close()


def test_device_pages_render(running_server):

    _, device_id = _seed_device()

    for path in ("/triage", "/devices", f"/devices/{device_id}"):
        status, body = _get(running_server + path)
        assert status == 200 and "router" in body, path

    # Coverage only lists sources plus quiet/invisible devices - the freshly
    # seeded "router" (state "new", status "seen") is neither, so it never
    # appears there; assert on the source row it does produce instead.
    status, body = _get(running_server + "/coverage")
    assert status == 200 and "lan" in body


def test_get_500s_are_plain_text_for_pages_and_json_for_api(running_server, monkeypatch):

    from atlas.devices.store import InventoryStore

    def boom(self, now=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(InventoryStore, "devices", boom)

    status, body = _get_allow_error(running_server + "/devices")
    assert status == 500 and body == "Internal error"

    status, body = _get_allow_error(running_server + "/api/devices")
    assert status == 500 and json.loads(body) == {"error": "internal error"}


def test_device_page_scans_devices_only_once(running_server, monkeypatch):
    """The device page used to call InventoryStore.devices() twice (once inside
    store.device(), once again to pass to the renderer) - now it's a single scan."""

    from atlas.devices.store import InventoryStore

    _, device_id = _seed_device()
    original = InventoryStore.devices
    calls = []

    def counting(self, now=None):
        calls.append(1)
        return original(self, now)

    monkeypatch.setattr(InventoryStore, "devices", counting)

    status, body = _get(running_server + f"/devices/{device_id}")

    assert status == 200 and "router" in body
    assert len(calls) == 1


def test_post_with_no_body_returns_400(running_server):

    _, device_id = _seed_device()
    url = f"{running_server}/api/devices/{device_id}"
    request = urllib.request.Request(url, method="POST", headers={"Origin": running_server})

    try:
        urllib.request.urlopen(request, timeout=5)
        pytest.fail("expected an HTTPError")
    except urllib.error.HTTPError as error:
        with error:
            assert error.code == 400


import hashlib
from pathlib import Path

PINNED = {
    "cytoscape.min.js": "5f3b5b529546d5af1fc5628590af033b74511a5b6f789f5f4682845863228b91",
}


def test_vendored_files_match_pinned_hashes():

    static = Path(__file__).resolve().parents[1] / "atlas" / "web" / "static"

    for name, digest in PINNED.items():
        assert hashlib.sha256((static / name).read_bytes()).hexdigest() == digest, name


def test_static_serves_only_allow_listed_files(running_server):

    with urllib.request.urlopen(running_server + "/static/cytoscape.min.js", timeout=5) as response:
        assert response.status == 200
        assert response.headers["Content-Type"] == "application/javascript; charset=utf-8"
        assert "max-age" in response.headers["Cache-Control"]
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert len(response.read()) > 100_000

    with urllib.request.urlopen(running_server + "/static/cytoscape.min.js?v=3.34.3", timeout=5) as response:
        assert response.status == 200

    for path in ("/static/README.md", "/static/../server.py", "/static/%2e%2e/server.py", "/static/", "/static/x.js",
                 "/static/cytoscape-dagre.js"):
        try:
            urllib.request.urlopen(running_server + path, timeout=5)
            raise AssertionError(f"{path} should be 404")
        except urllib.error.HTTPError as error:
            with error:
                assert error.code == 404, path
