"""
The inventory's JSON API for atlas web: plain (status, payload) results,
so the HTTP layer (server.py) owns sockets and headers and this module
owns only routing, validation mapping and events. Writes go through
InventoryStore, and every successful one is published as an event, the
same persistence path as every other atlas state change.
"""

import re
import sys
from datetime import datetime
from urllib.parse import unquote

import lanxang.web.chat as chat_module
from lanxang.config import load_config
from lanxang.core.application import application
from lanxang.devices.store import InventoryStore
from lanxang.events import AtlasEvent
from lanxang.intelligence.agent import AtlasAgent
from lanxang.intelligence.providers import get_provider
from lanxang.knowledge.queries import KnowledgeQueries
from lanxang.posture.model import WINDOWS, build_posture, node_details
from lanxang.posture.store import PostureStore
from lanxang.web.chat import ChatSessions, chat_turn, execute_step
from lanxang.web.graph import build_graph
from lanxang.clock import utcnow


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
        print(f"lanxang.web.api: event publish failed for {event_type}: {error!r}", file=sys.stderr)

    return 200, {"ok": True, **{key: value for key, value in result.items() if key != "found"}}


def _get(path, query=""):

    if path == "/api/posture":
        params = dict(part.partition("=")[::2] for part in query.split("&") if part)
        window = unquote(params.get("window", "24h"))
        if window not in WINDOWS:
            return 400, {"error": "window must be one of: " + ", ".join(WINDOWS)}
        return 200, build_posture(PostureStore(), utcnow(), window)

    if path == "/api/posture/node":
        params = dict(part.partition("=")[::2] for part in query.split("&") if part)
        details = node_details(PostureStore(), unquote(params.get("id", "")), utcnow())
        return (200, details) if details else NOT_FOUND

    store = InventoryStore()

    if path == "/api/devices":
        return 200, store.devices()

    if path == "/api/triage":
        return 200, store.triage()

    if path == "/api/coverage":
        return 200, store.coverage()

    if path == "/api/graph":
        return 200, build_graph(store.devices(), KnowledgeQueries().latest_topology(),
                                include_ignored="ignored=1" in query.split("&"),
                                include_wireless="wireless=1" in query.split("&"))

    match = DEVICE.match(path)

    if match:
        device = store.device(int(match.group(1)))
        return (200, device) if device else NOT_FOUND

    return None


def _post(path, body):

    if path == "/api/posture/known":

        if not isinstance(body, dict):
            return 400, {"error": "expected a JSON object"}

        result = PostureStore().mark_known(body.get("source"), body.get("asn_key"), body.get("note", ""))

        if not result["ok"]:
            return 400, {"error": result["error"]}

        try:
            application.runtime.events.publish(AtlasEvent(event_type="atlas.posture.marked_known", source="AtlasWeb",
                                                           payload={"source": body["source"], "asn_key": body["asn_key"]}))
        except Exception as error:
            print(f"lanxang.web.api: event publish failed for atlas.posture.marked_known: {error!r}", file=sys.stderr)

        return 200, result

    if path == "/api/access/known":

        if not isinstance(body, dict) or not body.get("user") or not body.get("place_key"):
            return 400, {"error": "expected {user, place_key}"}

        from lanxang.access.store import AccessStore
        result = AccessStore().confirm_place(str(body["user"]), str(body["place_key"]))

        if not result["ok"]:
            return 400, {"error": result["error"]}

        try:
            application.runtime.events.publish(AtlasEvent(event_type="atlas.access.place_confirmed", source="AtlasWeb",
                                                           payload={"user": body["user"], "place_key": body["place_key"]}))
        except Exception as error:
            print(f"lanxang.web.api: event publish failed for atlas.access.place_confirmed: {error!r}", file=sys.stderr)

        return 200, result

    if path in ("/api/chat", "/api/actions/execute"):

        if not isinstance(body, dict):
            return 400, {"error": "expected a JSON object"}

        if path == "/api/chat":
            return chat_turn(SESSIONS, body.get("session"), body.get("message"), _agent, tools=body.get("tools", True))

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
        if path == "/api/wiring/refresh":
            return _wiring_refresh()
        if path.startswith("/api/uptime/"):
            from lanxang.web.uptime_page import handle_post
            return handle_post(path, body) or (404, {"error": "not found"})
        if path.startswith("/api/alerts/"):
            from lanxang.web.alerts_page import handle_post
            return handle_post(path, body)
        if path.startswith("/api/settings/"):
            from lanxang.web.settings_page import handle_post
            return handle_post(path, body)
        return _post(path, body)

    return None


def _wiring_refresh():
    """The /cabling Refresh button: one synchronous wiring scan (seconds), same code as `atlas wiring scan`."""

    from lanxang.wiring.scan import WiringBusy, run_scan
    from lanxang.wiring.store import WiringStore

    settings = load_config()

    if not settings.wiring.enabled:
        return 400, {"error": "wiring is not enabled in atlas.yaml"}

    try:
        result = run_scan(settings, WiringStore(), InventoryStore().devices())
    except WiringBusy:
        return 409, {"error": "a scan is already running"}

    snapshot = result["snapshot"]
    try:
        application.runtime.events.publish(AtlasEvent(
            event_type="atlas.wiring.scanned", source="AtlasWeb",
            payload={"links": len(snapshot["links"]), "warnings": len(snapshot["warnings"]),
                     "sources": {name: source["ok"] for name, source in result["sources"].items()}}))
    except Exception as error:
        print(f"lanxang.web.api: event publish failed for atlas.wiring.scanned: {error!r}", file=sys.stderr)

    return 200, {"ok": True, "taken_at": result["taken_at"].isoformat(), "sources": result["sources"]}
