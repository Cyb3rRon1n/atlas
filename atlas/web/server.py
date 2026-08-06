"""
A local, read-only HTTP server over Atlas's existing stored data - no
new dependency, stdlib http.server only, matching this project's
"lightweight" scoping for this feature. Every route is a GET; there is
no POST route and no route calls into atlas.docker/atlas.proxmox/
atlas.actions at all, so there is no write path reachable from this
module by construction, not just by convention.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from atlas.knowledge.queries import KnowledgeQueries
from atlas.reporting.trends import build_trends_payload
from atlas.web.render import render_history_page, render_overview_page, render_trends_page


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
        else:
            self._send(404, "text/plain; charset=utf-8", "Not found")
            return

        self._send(200, "text/html; charset=utf-8", body)

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
