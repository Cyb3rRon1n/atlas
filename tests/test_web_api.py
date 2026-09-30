from atlas.core.application import application
from atlas.devices import Sighting
from atlas.devices.store import InventoryStore
from atlas.knowledge.queries import KnowledgeQueries
from atlas.web import api


def two_devices():

    store = InventoryStore()
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01", hostname="router"),
                             Sighting("lan", "aa:02", ip="192.168.10.2", mac="aa:02")])

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
