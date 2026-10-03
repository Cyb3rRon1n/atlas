"""
The inventory's JSON API for atlas web: plain (status, payload) results,
so the HTTP layer (server.py) owns sockets and headers and this module
owns only routing, validation mapping and events. Writes go through
InventoryStore, and every successful one is published as an event, the
same persistence path as every other atlas state change.
"""

import re
import sys

import atlas.web.chat as chat_module
from atlas.config import load_config
from atlas.core.application import application
from atlas.devices.store import InventoryStore
from atlas.events import AtlasEvent
from atlas.intelligence.agent import AtlasAgent
from atlas.intelligence.providers import get_provider
from atlas.knowledge.queries import KnowledgeQueries
from atlas.web.chat import ChatSessions, chat_turn, execute_step
from atlas.web.graph import build_graph


DEVICE = re.compile(r"^/api/devices/(\d+)$")

MERGE = re.compile(r"^/api/devices/(\d+)/merge$")

SPLIT = re.compile(r"^/api/sightings/(\d+)/split$")

NOT_FOUND = (404, {"error": "not found"})

SESSIONS = ChatSessions()


class LiveStateError(Exception):
    """_environment() itself failed (Docker/Proxmox down) while re-grounding an approved action."""


def _agent():

    settings = load_config()

    return AtlasAgent(get_provider(settings.intelligence), settings)


def _environment():

    return AtlasAgent(None, load_config())._live_environment()


def _safe_environment():
    """Wraps _environment() so execute_step's caller can tell "state changed" apart from "couldn't check"."""

    try:
        return _environment()

    except Exception as error:
        raise LiveStateError(str(error)) from error


def _result(result, event_type, payload):

    if not result.get("found"):
        return NOT_FOUND

    if result.get("error"):
        return 400, {"error": result["error"]}

    try:
        application.runtime.events.publish(AtlasEvent(event_type=event_type, source="AtlasWeb", payload=payload))
    except Exception as error:
        # The store change already committed - a broken event listener shouldn't turn
        # a successful write into an error response the caller would wrongly retry.
        print(f"atlas.web.api: event publish failed for {event_type}: {error!r}", file=sys.stderr)

    return 200, {"ok": True, **{key: value for key, value in result.items() if key != "found"}}


def _get(path, query=""):

    store = InventoryStore()

    if path == "/api/devices":
        return 200, store.devices()

    if path == "/api/triage":
        return 200, store.triage()

    if path == "/api/coverage":
        return 200, store.coverage()

    if path == "/api/graph":
        return 200, build_graph(store.devices(), KnowledgeQueries().latest_topology(),
                                include_ignored="ignored=1" in query.split("&"))

    match = DEVICE.match(path)

    if match:
        device = store.device(int(match.group(1)))
        return (200, device) if device else NOT_FOUND

    return None


def _post(path, body):

    if path in ("/api/chat", "/api/actions/execute"):

        if not isinstance(body, dict):
            return 400, {"error": "expected a JSON object"}

        if path == "/api/chat":
            return chat_turn(SESSIONS, body.get("session"), body.get("message"), _agent)

        try:
            return execute_step(body.get("action"), _safe_environment, executor=chat_module.execute_action)

        except LiveStateError as error:
            return 503, {"error": f"could not check live state: {error}"}

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

    path, _, query = path.partition("?")

    if method == "GET":
        return _get(path, query)

    if method == "POST":
        return _post(path, body)

    return None
