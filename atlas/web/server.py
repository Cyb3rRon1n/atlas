"""
A local HTTP server over Atlas's existing stored data - no new
dependency, stdlib http.server only, matching this project's
"lightweight" scoping for this feature. The server is read-only except
for the device inventory's /api/* POST routes: those are gated by a
same-origin check, capped at 64 KB of JSON, and write only through
InventoryStore. The Authelia admin rule in front of the host is the
auth boundary - this module doesn't authenticate requests itself.
"""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from atlas.devices.store import InventoryStore
from atlas.knowledge.queries import KnowledgeQueries
from atlas.reporting.trends import build_trends_payload
from atlas.web import api
from atlas.web.devices_pages import render_coverage_page, render_device_page, render_devices_page, render_triage_page
from atlas.web.render import build_summary, render_history_page, render_map_page, render_overview_page, render_trends_page


MAX_BODY = 65536

DEVICE_PAGE = re.compile(r"^/devices/(\d+)$")


def same_origin(headers):
    """
    Cross-site request forgery guard for the write routes: Authelia's cookie rides along
    on any request the browser makes, so a POST must provably come from atlas's own pages.
    """

    if headers.get("Sec-Fetch-Site") == "same-origin":
        return True

    origin = headers.get("Origin") or headers.get("Referer") or ""
    host = headers.get("Host") or ""

    return bool(origin and host) and urlsplit(origin).netloc == host


class AtlasWebHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        path = self.path.split("?", 1)[0]
        query = KnowledgeQueries()

        if path == "/":
            body = render_overview_page(query.latest_environment(), query.latest_analysis())
        elif path == "/history":
            body = render_history_page(query.recent_events(50))
        elif path == "/trends":
            body = render_trends_page(build_trends_payload())
        elif path == "/map":
            body = render_map_page(query.latest_topology())
        elif path == "/api/summary":
            self._send(200, "application/json",
                       json.dumps(build_summary(query.latest_topology(), InventoryStore().devices())))
            return
        elif path == "/triage":
            body = render_triage_page(InventoryStore().triage())
        elif path == "/devices":
            body = render_devices_page(InventoryStore().devices())
        elif path == "/coverage":
            body = render_coverage_page(InventoryStore().coverage())
        elif DEVICE_PAGE.match(path):
            store = InventoryStore()
            device = store.device(int(DEVICE_PAGE.match(path).group(1)))
            if device is None:
                self._send(404, "text/plain; charset=utf-8", "Not found")
                return
            body = render_device_page(device, store.devices())
        elif path.startswith("/api/"):
            result = api.handle("GET", path)
            if result is None:
                self._send(404, "application/json", json.dumps({"error": "not found"}))
            else:
                self._send(result[0], "application/json", json.dumps(result[1]))
            return
        else:
            self._send(404, "text/plain; charset=utf-8", "Not found")
            return

        self._send(200, "text/html; charset=utf-8", body)

    def do_POST(self):

        path = self.path.split("?", 1)[0]

        if not same_origin(self.headers):
            self._send(403, "application/json", json.dumps({"error": "cross-origin request refused"}))
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1

        if length < 0 or length > MAX_BODY:
            self.close_connection = True  # the unread body must not be parsed as a next request
            self._send(413 if length > MAX_BODY else 400, "application/json",
                       json.dumps({"error": "body must be JSON, at most 64 KB"}))
            return

        try:
            body = json.loads(self.rfile.read(length) or b"null")
        except (ValueError, RecursionError):
            # RecursionError: json's decoder recurses per nesting level, so deeply
            # nested input (still under MAX_BODY in byte size) can blow the stack
            # rather than raise a normal decode error - treat it the same way.
            self._send(400, "application/json", json.dumps({"error": "body must be valid JSON"}))
            return

        try:
            result = api.handle("POST", path, body)
        except Exception as error:
            self.log_error("unhandled error in POST %s: %r", path, error)
            self._send(500, "application/json", json.dumps({"error": "internal error"}))
            return

        if result is None:
            self._send(404, "application/json", json.dumps({"error": "not found"}))
        else:
            self._send(result[0], "application/json", json.dumps(result[1]))

    def _send(self, status, content_type, body):

        encoded = body.encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_server(host="127.0.0.1", port=8420):
    """
    Blocks until interrupted (Ctrl+C) - on-demand like every other
    Atlas command, not a background/daemon process; the user starts
    it explicitly in a foreground terminal and stops it the same way.
    """

    httpd = ThreadingHTTPServer((host, port), AtlasWebHandler)

    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
