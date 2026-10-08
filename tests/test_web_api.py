from datetime import datetime

from atlas.core.application import application
from atlas.devices import Sighting
from atlas.devices.store import InventoryStore
from atlas.intelligence.providers.base import AIProviderError, ChatReply, SuggestedAction
from atlas.knowledge.queries import KnowledgeQueries
from atlas.web import api


def two_devices():

    store = InventoryStore()
    # Globally-assigned-looking MACs (first octet's locally-administered bit unset) -
    # atlas.devices.wiring guesses "wireless" from that bit, and these two devices
    # need to default to visible/non-wireless for the rest of this module's tests.
    store.record_run("lan", [Sighting("lan", "00:01", ip="192.168.10.1", mac="00:01", hostname="router"),
                             Sighting("lan", "00:02", ip="192.168.10.2", mac="00:02")])

    return {d["name"]: d["id"] for d in store.devices()}


def test_get_routes(temp_db):

    ids = two_devices()

    status, devices = api.handle("GET", "/api/devices")
    assert status == 200 and {d["name"] for d in devices} == {"router", "192.168.10.2"}
    assert api.handle("GET", f"/api/devices/{ids['router']}")[1]["name"] == "router"
    assert api.handle("GET", "/api/devices/999") == (404, {"error": "not found"})
    assert set(api.handle("GET", "/api/triage")[1]) == {"new", "quiet"}
    assert set(api.handle("GET", "/api/coverage")[1]) == {"sources", "quiet", "invisible"}
    assert api.handle("GET", "/api/summary") is None
    assert api.handle("GET", "/nope") is None


def test_edit_publishes_event_and_maps_errors(temp_db):

    ids = two_devices()

    assert api.handle("POST", f"/api/devices/{ids['router']}", {"name": "UniFi", "kind": "network"}) == (200, {"ok": True})
    assert InventoryStore().device(ids["router"])["name"] == "UniFi"
    assert KnowledgeQueries().recent_events(5)[0].event_type == "atlas.devices.updated"

    status, payload = api.handle("POST", f"/api/devices/{ids['router']}", {"kind": "toaster"})
    assert status == 400 and "kind must be one of" in payload["error"]
    assert api.handle("POST", "/api/devices/999", {"name": "x"}) == (404, {"error": "not found"})
    assert api.handle("POST", f"/api/devices/{ids['router']}", ["not", "an", "object"]) == \
        (400, {"error": "expected a JSON object"})


def test_publish_failure_still_returns_200_and_the_change_persists(temp_db, monkeypatch):

    ids = two_devices()

    def boom(event):
        raise RuntimeError("event bus is down")

    monkeypatch.setattr(application.runtime.events, "publish", boom)

    status, payload = api.handle("POST", f"/api/devices/{ids['router']}", {"name": "UniFi"})

    assert status == 200 and payload == {"ok": True}
    assert InventoryStore().device(ids["router"])["name"] == "UniFi"


def test_merge_and_split(temp_db):

    ids = two_devices()
    router, other = ids["router"], ids["192.168.10.2"]

    assert api.handle("POST", f"/api/devices/{other}/merge", {"into": True}) == (400, {"error": "into must be a device id"})
    assert api.handle("POST", f"/api/devices/{other}/merge", {"into": router}) == (200, {"ok": True, "device_id": router})
    assert KnowledgeQueries().recent_events(5)[0].event_type == "atlas.devices.merged"

    sighting = InventoryStore().device(router)["sightings"][-1]["id"]
    status, payload = api.handle("POST", f"/api/sightings/{sighting}/split", {})
    assert status == 200 and payload["ok"] is True and payload["device_id"] != router
    assert KnowledgeQueries().recent_events(5)[0].event_type == "atlas.devices.split"
    assert api.handle("POST", "/api/other", {}) is None


def test_graph_route(temp_db):

    ids = two_devices()
    router_node = f"d{ids['router']}"

    status, graph = api.handle("GET", "/api/graph")
    assert status == 200 and {"internet", "lan"} <= {node["data"]["id"] for node in graph["nodes"]}
    assert router_node in {node["data"]["id"] for node in graph["nodes"]}

    InventoryStore().set_fields(ids["router"], {"state": "ignored"})

    status, graph = api.handle("GET", "/api/graph")
    assert status == 200 and router_node not in {node["data"]["id"] for node in graph["nodes"]}

    status, graph = api.handle("GET", "/api/graph?ignored=1")
    assert status == 200 and router_node in {node["data"]["id"] for node in graph["nodes"]}

    other_node = f"d{ids['192.168.10.2']}"
    InventoryStore().set_fields(ids["192.168.10.2"], {"connection": "wireless"})

    status, graph = api.handle("GET", "/api/graph")
    assert status == 200 and other_node not in {node["data"]["id"] for node in graph["nodes"]}
    assert graph["hidden_wireless"] == 1

    status, graph = api.handle("GET", "/api/graph?wireless=1")
    assert status == 200 and other_node in {node["data"]["id"] for node in graph["nodes"]}
    assert graph["hidden_wireless"] == 0


class StubAgent:

    def converse(self, messages):
        return ChatReply(text=f"you said {messages[-1]['content']}", action=SuggestedAction("restart_container", "sonarr"))


def test_chat_route(temp_db, monkeypatch):

    monkeypatch.setattr(api, "_agent", lambda: StubAgent())

    status, payload = api.handle("POST", "/api/chat", {"message": "hi"})
    assert status == 200 and payload["text"] == "you said hi" and payload["action"]["command"] == "atlas restart sonarr"

    again = api.handle("POST", "/api/chat", {"message": "again", "session": payload["session"]})[1]
    assert again["session"] == payload["session"]


def test_chat_route_maps_provider_error_to_502(temp_db, monkeypatch):

    def boom():
        raise AIProviderError("no key")

    monkeypatch.setattr(api, "_agent", boom)

    assert api.handle("POST", "/api/chat", {"message": "hi"}) == (502, {"error": "no key"})


def test_execute_route(temp_db, monkeypatch):

    monkeypatch.setattr(api, "_environment", lambda: {"containers": {"Docker": {"containers": [{"name": "sonarr"}]}}})
    monkeypatch.setattr("atlas.web.chat.execute_action", lambda action: {"success": True})

    assert api.handle("POST", "/api/actions/execute", {"action": {"type": "restart_container", "target": "sonarr"}}) == \
        (200, {"ok": True, "result": {"success": True}})
    assert api.handle("POST", "/api/actions/execute", {"action": {"type": "restart_container", "target": "nope"}})[0] == 409


def test_execute_route_maps_live_state_failure_to_503(temp_db, monkeypatch):

    def boom():
        raise RuntimeError("docker down")

    monkeypatch.setattr(api, "_environment", boom)

    assert api.handle("POST", "/api/actions/execute", {"action": {"type": "restart_container", "target": "sonarr"}}) == \
        (503, {"error": "could not check live state: docker down"})


def test_posture_endpoints(temp_db):
    from atlas.posture.store import PostureStore
    from atlas.web import api
    store = PostureStore(temp_db)
    store.set_status("conntrack", True, {"flows": 1}, datetime.utcnow())
    status, body = api.handle("GET", "/api/posture?window=1h")
    assert status == 200 and {"strip", "nodes", "edges", "bands", "exposure", "review"} <= set(body)
    assert api.handle("GET", "/api/posture?window=bogus")[0] == 400
    assert api.handle("GET", "/api/posture/node?id=dst:AS1")[0] == 404
    assert api.handle("POST", "/api/posture/known", {"source": "sonarr", "asn_key": "AS64500"}) == (200, {"ok": True})
    assert api.handle("POST", "/api/posture/known", {"source": "sonarr", "asn_key": "x"})[0] == 400
    assert api.handle("POST", "/api/posture/known", ["x"])[0] == 400
