"""
The inventory's JSON API for atlas web: plain (status, payload) results,
so the HTTP layer (server.py) owns sockets and headers and this module
owns only routing, validation mapping and events. Writes go through
InventoryStore, and every successful one is published as an event, the
same persistence path as every other atlas state change.
"""

import re

from atlas.core.application import application
from atlas.devices.store import InventoryStore
from atlas.events import AtlasEvent


DEVICE = re.compile(r"^/api/devices/(\d+)$")

MERGE = re.compile(r"^/api/devices/(\d+)/merge$")

SPLIT = re.compile(r"^/api/sightings/(\d+)/split$")

NOT_FOUND = (404, {"error": "not found"})


def _result(result, event_type, payload):

    if not result.get("found"):
        return NOT_FOUND

    if result.get("error"):
        return 400, {"error": result["error"]}

    application.runtime.events.publish(AtlasEvent(event_type=event_type, source="AtlasWeb", payload=payload))

    return 200, {"ok": True, **{key: value for key, value in result.items() if key != "found"}}


def _get(path):

    store = InventoryStore()

    if path == "/api/devices":
        return 200, store.devices()

    if path == "/api/triage":
        return 200, store.triage()

    if path == "/api/coverage":
        return 200, store.coverage()

    match = DEVICE.match(path)

    if match:
        device = store.device(int(match.group(1)))
        return (200, device) if device else NOT_FOUND

    return None


def _post(path, body):

    if not any(pattern.match(path) for pattern in (DEVICE, MERGE, SPLIT)):
        return None

    if not isinstance(body, dict):
        return 400, {"error": "expected a JSON object"}

    store = InventoryStore()
    match = DEVICE.match(path)

    if match:
        device_id = int(match.group(1))
        return _result(store.set_fields(device_id, body), "atlas.devices.updated",
                       {"device_id": device_id, "fields": body})

    match = MERGE.match(path)

    if match:

        into = body.get("into")

        if isinstance(into, bool) or not isinstance(into, int):
            return 400, {"error": "into must be a device id"}

        device_id = int(match.group(1))
        return _result(store.merge(device_id, into), "atlas.devices.merged", {"device_id": device_id, "into": into})

    sighting_id = int(SPLIT.match(path).group(1))

    return _result(store.split(sighting_id), "atlas.devices.split", {"sighting_id": sighting_id})


def handle(method, path, body=None):

    if method == "GET":
        return _get(path)

    if method == "POST":
        return _post(path, body)

    return None
