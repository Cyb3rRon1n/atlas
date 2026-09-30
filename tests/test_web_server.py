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
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01", hostname="router")])

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


def test_api_get_and_summary_counts(running_server):

    _seed_device()

    status, body = _get(running_server + "/api/devices")
    assert status == 200 and json.loads(body)[0]["name"] == "router"

    summary = json.loads(_get(running_server + "/api/summary")[1])
    assert summary["to_triage"] == 1 and summary["devices_quiet"] == 0


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
