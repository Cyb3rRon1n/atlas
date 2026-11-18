"""
A local HTTP server over Atlas's existing stored data - no new
dependency, stdlib http.server only, matching this project's
"lightweight" scoping for this feature. The server is read-only except
for the device inventory's /api/* POST routes: those are gated by a
same-origin check, capped at 64 KB of JSON, and write only through
InventoryStore. Sign-in is atlas.web.auth (web.auth: builtin, the default)
or, with web.auth: proxy, the auth proxy in front of the host.
"""

import json
import re
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, quote, urlsplit

import psutil

from atlas.config.loader import load_config
from atlas.web import render as web_render
from atlas.alerts import AlertStore
from atlas.devices import identify
from atlas.devices.store import InventoryStore
from atlas.discovery.host_health import get_host_health
from atlas.knowledge.queries import KnowledgeQueries
from atlas.posture.model import build_posture, build_trends
from atlas.posture.store import PostureStore
from atlas.web import api
from atlas.web.auth import COOKIE, SESSION_SECONDS
from atlas.web.chat_page import render_chat_page
from atlas.web.login_page import render_login_page, render_setup_page
from atlas.web.devices_pages import render_coverage_page, render_device_page, render_devices_page, render_triage_page
from atlas.web.hosts_page import render_hosts_summary
from atlas.access.store import AccessStore
from atlas.web.access_page import WINDOWS as ACCESS_WINDOWS, render_access_page
from atlas.web.home_page import (build_hosts, build_stats, build_storage, interesting_events, parse_mdstat, render_home_page,
                                 setup_steps)
from atlas.web.posture_page import render_posture_page
from atlas.web.graph import build_graph
from atlas.web.network_page import render_network_page
from atlas.web.cabling_page import cabling_csv, render_cabling_page
from atlas.web.render import _posture_block, build_summary, render_history_page, render_overview_page
from atlas.web.trends_page import WINDOWS as TREND_WINDOWS, render_trends_page
from atlas.clock import utcnow


MAX_BODY = 65536

DEVICE_PAGE = re.compile(r"^/devices/(\d+)$")

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Explicit allow-list - never build a filesystem path from the request.
STATIC_FILES = {"cytoscape.min.js", "elk.bundled.js"}


def _latest_wiring():
    """Latest wiring snapshot, or None when the wired map is off or never ran - a device page never fails over it."""

    try:
        from atlas.wiring.store import WiringStore
        rows = WiringStore().latest(1)
        return rows[0]["snapshot"] if rows else None
    except Exception:
        return None


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


def safe_next(value):
    """Only same-site paths after sign-in - never an open redirect to //evil or a full URL."""

    value = value or "/"

    return value if value.startswith("/") and not value.startswith("//") and "\\" not in value else "/"



def _notify_settings():
    """notify: settings for the Alerts page's quiet hours, or None if atlas.yaml can't be read."""

    try:
        return load_config().notify
    except Exception:
        return None

class AtlasWebHandler(BaseHTTPRequestHandler):

    auth = None     # an atlas.web.auth.Auth when web.auth is builtin; None = an auth proxy guards the host

    def _session_ok(self):

        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
        except Exception:
            return False
        morsel = cookie.get(COOKIE)

        return bool(morsel) and self.auth.valid_session(morsel.value)

    def _token_ok(self):

        header = self.headers.get("Authorization") or ""
        token = header[7:].strip() if header.lower().startswith("bearer ") else self.headers.get("X-API-Key") or ""

        return self.auth.valid_token(token.strip())

    def _redirect(self, location, cookie=None):

        self.send_response(303)
        self.send_header("Location", location)
        if cookie is not None:
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            max_age = SESSION_SECONDS if cookie else 0
            self.send_header("Set-Cookie", f"{COOKIE}={cookie}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax{secure}")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _gate(self, path):
        """
        True when a GET may go on to the page. Otherwise the response (sign-in,
        setup, redirect or 401) has been sent here. The API token opens GET /api/* only.
        """

        if path.startswith("/static/"):
            return True

        if not self.auth.configured():
            if path == "/setup":
                self._send(200, "text/html; charset=utf-8", render_setup_page())
            elif path.startswith("/api/"):
                self._send(401, "application/json", json.dumps({"error": "atlas is not set up yet"}))
            else:
                self._redirect("/setup")
            return False

        if path in ("/login", "/setup"):
            if self._session_ok():
                self._redirect("/")
            else:
                next_path = safe_next((parse_qs(self.path.partition("?")[2]).get("next") or ["/"])[0])
                self._send(200, "text/html; charset=utf-8", render_login_page(next_path=next_path))
            return False

        if self._session_ok() or ((path.startswith("/api/") or path == "/metrics") and self._token_ok()):
            return True

        if path == "/metrics":
            self._send(401, "text/plain; charset=utf-8", "sign in or send the API token (Authorization: Bearer ...)")
        elif path.startswith("/api/"):
            self._send(401, "application/json", json.dumps({"error": "sign in or send the API token"}))
        else:
            self._redirect("/login?next=" + quote(safe_next(self.path), safe="/"))
        return False

    def _auth_form(self, path, form):
        """POST /login, /setup, /logout (urlencoded forms from the pages above)."""

        field = lambda name: (form.get(name) or [""])[0]
        client = self.client_address[0]

        if path == "/logout":
            if self._session_ok():          # only a signed-in browser can sign everyone out
                self.auth.end_sessions()
            self._redirect("/login", cookie="")
            return

        if path == "/setup":
            if self.auth.configured():
                self._redirect("/login")
                return
            if not self.auth.check_setup_code(field("code")):
                # wrong codes count against the same per-client limit as wrong passwords
                self.auth.login("", client)
                error = "Too many attempts - wait a few minutes." if self.auth.limited(client) else "That setup code is not right."
                self._send(403, "text/html; charset=utf-8", render_setup_page(error))
                return
            if field("password") != field("confirm"):
                self._send(400, "text/html; charset=utf-8", render_setup_page("The passwords don't match."))
                return
            try:
                self.auth.set_password(field("password"))
            except ValueError as error:
                self._send(400, "text/html; charset=utf-8", render_setup_page(str(error).capitalize() + "."))
                return
            self._redirect("/", cookie=self.auth.session())
            return

        # /login
        next_path = safe_next(field("next"))
        result = self.auth.login(field("password"), client)
        if result == "limited":
            self._send(429, "text/html; charset=utf-8",
                       render_login_page("Too many attempts - wait a few minutes.", next_path))
        elif result is None:
            self.log_message("failed sign-in from %s", client)
            self._send(401, "text/html; charset=utf-8", render_login_page("Wrong password.", next_path))
        else:
            self._redirect(next_path, cookie=result)

    def _home_data(self, query):
        """
        (posture, hosts, events) for the home page. Each source is fetched on
        its own so one failing (no posture DB, no Proxmox scan yet) only
        blanks its own card.
        """

        def safe(label, fetch):
            try:
                return fetch()
            except Exception as error:
                self.log_error("home: %s failed: %r", label, error)
                return None

        now = utcnow()
        settings = safe("config", load_config)
        health_settings = settings.health if settings else None
        topology = safe("topology", query.latest_topology)
        pve_scan = safe("proxmox scan", lambda: query.latest_event_payload("atlas.proxmox.scan.completed"))
        host_issues = safe("host issues", lambda: ((PostureStore().statuses().get("host") or {}).get("detail")
                                                    or {}).get("issues"))
        local = safe("host health", lambda: get_host_health(health_settings.status_urls if health_settings else None))

        def usage():
            return {label: psutil.disk_usage(path) for label, path in (health_settings.storage_paths or {}).items()}

        posture = safe("posture", lambda: _posture_block(build_posture(PostureStore(), now, "24h")))
        storage = build_storage(safe("mdstat", lambda: parse_mdstat(Path("/proc/mdstat").read_text())) or [],
                                (safe("storage paths", usage) if health_settings else None) or {},
                                (local or {}).get("status_feeds"), pve_scan, topology, health_settings,
                                safe("nas", lambda: (PostureStore().statuses().get("nas") or {}).get("detail"))
                                if settings and settings.nas.enabled else None)

        from atlas.monitoring.uptime import UptimeStore

        devices = safe("devices", lambda: InventoryStore().devices())
        hosts = build_hosts(topology, local, pve_scan, host_issues)
        checks = settings.uptime.checks if settings else []
        uptime = safe("uptime", lambda: [info["uptime"].get("7 days") for info in
                                         UptimeStore().summary([c.name for c in checks], now).values()])
        ups = safe("ups", lambda: (PostureStore().statuses().get("ups") or {}).get("detail")) \
            if settings and settings.ups.enabled else None

        last = safe("internet", lambda: UptimeStore().latest("Internet"))
        internet = None
        if last and settings and settings.internet.enabled and now - last[0] < timedelta(minutes=5):
            internet = last[1:]                         # (up, ms); an old result means the check isn't running

        ha = safe("homeassistant", lambda: (PostureStore().statuses().get("homeassistant") or {}).get("detail")) \
            if settings and settings.homeassistant.enabled else None
        dns = safe("dns", lambda: (PostureStore().statuses().get("dns") or {}).get("detail")) \
            if settings and settings.dns_filter.enabled else None

        return dict(
            dns=dns, names={d["ip"]: d["name"] for d in devices or [] if d.get("ip")}, ha=ha,
            stats=build_stats(devices, hosts, storage, posture, uptime, ups, internet, dns, ha),
            posture=posture, hosts=hosts,
            events=interesting_events(safe("events", lambda: query.recent_events(200)) or []),
            storage=storage, trends=safe("trends", lambda: build_trends(PostureStore(), now)),
            analysis=safe("analysis", query.latest_analysis), now=now,
            access_reviews=safe("access reviews", lambda: AccessStore().places("review")) or [],
            open_alerts=safe("alerts", lambda: AlertStore().listing(now)["open"]) or [],
            steps=safe("setup steps", lambda: setup_steps(settings, devices or [])) if settings else None)

    def do_GET(self):

        path = self.path.split("?", 1)[0]

        if path == "/healthz":
            self._send(200, "text/plain; charset=utf-8", "ok")
            return

        if path.startswith("/ping/"):                  # heartbeats: the token in the address is the password
            self._ping(path)
            return

        if path == "/metrics":                         # Prometheus: signed in, or the API token as a Bearer
            from atlas.web.metrics import collect, render
            if self.auth and not self._gate(path):
                return
            self._send(200, "text/plain; version=0.0.4; charset=utf-8",
                       render(collect(load_config(), utcnow())))
            return

        if self.auth and not self._gate(path):
            return

        try:                                           # no chat panel while no AI is set up
            web_render.AI_ON = load_config().intelligence.provider != "none"
        except Exception:
            web_render.AI_ON = True

        query = KnowledgeQueries()

        if path == "/":
            body = render_home_page(**self._home_data(query))
        elif path == "/posture":
            body = render_posture_page()
        elif path == "/settings":
            from atlas.web.settings_page import render_settings_page
            body = render_settings_page()
        elif path == "/overview":
            home = self._home_data(query)
            body = render_overview_page(query.latest_environment(), query.latest_analysis(),
                                        render_hosts_summary(home["hosts"], home["storage"], query.latest_topology()))
        elif path == "/access":
            from datetime import timedelta
            settings = load_config()
            window = (parse_qs(self.path.partition("?")[2]).get("window") or ["7d"])[0]
            window = window if window in ACCESS_WINDOWS else "7d"
            summary = AccessStore().summary(utcnow() - timedelta(days=ACCESS_WINDOWS[window]))
            body = render_access_page(summary, window, settings.access.home_ips, settings.access.enabled,
                                      AccessStore().places())
        elif path == "/alerts":
            from atlas.web.alerts_page import render_alerts_page
            now = utcnow()
            body = render_alerts_page(AlertStore().listing(now), now, _notify_settings())
        elif path == "/history":
            from atlas.web import changes_feed
            window = (parse_qs(self.path.partition("?")[2]).get("changes") or ["24h"])[0]
            window = window if window in changes_feed.WINDOWS else "24h"
            events, now = query.recent_events(300), utcnow()
            feed = changes_feed.collect(now, window, {
                "alerts": lambda at, days: AlertStore().listing(at, days), "devices": InventoryStore().devices,
                "changes": lambda since: [(at, kind, payload) for kind in changes_feed.CHANGE_EVENTS
                                          for at, payload in query.events_since([kind], since)]})
            body = render_history_page(events, changes=changes_feed.render(feed, now, window))
        elif path == "/uptime":
            from atlas.config import local
            from atlas.monitoring.uptime import UptimeStore
            from atlas.web.uptime_page import internet_data, render_uptime_page, suggestions
            settings, now = load_config(), utcnow()
            checks = settings.uptime.checks
            power = None
            if settings.ups.enabled:
                power = (PostureStore().statuses().get("ups") or {}).get("detail") or {"error": "not read yet"}
            store = UptimeStore()
            body = render_uptime_page(checks, store.summary([c.name for c in checks], now), now,
                                      settings.uptime.fail_after, suggestions(checks), local.locked(("uptime", "checks")),
                                      power, internet_data(store, now, settings.uptime.fail_after, settings.internet)
                                      if settings.internet.enabled else None, self._beats(settings, now),
                                      local.locked(("uptime", "heartbeats")))
        elif path == "/trends":
            from datetime import timedelta
            window = (parse_qs(self.path.partition("?")[2]).get("window") or ["24h"])[0]
            window = window if window in TREND_WINDOWS else "24h"
            now = utcnow()
            since = now - timedelta(days=TREND_WINDOWS[window])
            topology = query.latest_topology() or {}
            pve = (topology.get("proxmox") or {}).get("host")
            lan = {h.get("address"): h["name"] for h in topology.get("lan", [])}
            scans = query.events_since(["atlas.proxmox.scan.completed"], since)
            node_set = {n["name"] for _, p in scans for n in p.get("nodes", [])}
            # a single-node install is the LAN host at the Proxmox address - show the name people use (as on Home)
            names = {next(iter(node_set)): lan[pve]} if len(node_set) == 1 and pve in lan else {}
            body = render_trends_page(query.events_since(["atlas.host.sample"], since), scans, window, now,
                                      topology.get("host") or "this host", names)
        elif path == "/map":
            topology = query.latest_topology()
            body = render_network_page(topology, PostureStore().latest_routes(),
                                       build_graph(InventoryStore().devices(), topology))
        elif path in ("/cabling", "/cabling.csv"):
            from atlas.wiring.store import WiringStore, diff_snapshots
            try:
                rows = WiringStore().latest(2)
                if path == "/cabling.csv":
                    if not rows:
                        self._send(404, "text/plain; charset=utf-8", "No wiring scan yet")
                        return
                    data = cabling_csv(rows[0]["snapshot"]).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="cabling.csv"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                changes = diff_snapshots(rows[1]["snapshot"], rows[0]["snapshot"]) if len(rows) > 1 else []
                from atlas.wiring.cabling import load_cabling
                wiring = load_config().wiring
                # cabling.yaml is read on every view, so a faceplate/label edit shows without a rescan
                from atlas.wiring import suggest, traffic
                body = render_cabling_page(rows[0] if rows else None, changes, wiring.enabled,
                                           faceplates=load_cabling(wiring.cabling_file)["faceplates"],
                                           suggested=suggest.current(),
                                           history=traffic.history(WiringStore().engine))
            except Exception as error:
                self.log_error("unhandled error in GET %s: %r", path, error)
                self._send(500, "text/plain; charset=utf-8", "Internal error")
                return
        elif path == "/chat":
            try:
                prefill = ""
                query_string = self.path.partition("?")[2]
                params = parse_qs(query_string)
                if "q" in params:
                    prefill = params["q"][0][:2000]
                else:
                    match = re.search(r"(?:^|&)device=(\d+)", query_string)
                    if match:
                        device = InventoryStore().device(int(match.group(1)))
                        if device:
                            sources = ", ".join(sorted({sighting["source"] for sighting in device["sightings"]}))
                            name = device["name"] or device["ip"] or f"device {device['id']}"
                            prefill = (f"Tell me about {name} ({device['ip'] or 'no ip'}): it is {device['status']}, "
                                       f"state {device['state']}, seen by {sources}. Anything wrong with it?")
                body = render_chat_page(prefill)
            except Exception as error:
                self.log_error("unhandled error in GET %s: %r", path, error)
                self._send(500, "text/plain; charset=utf-8", "Internal error")
                return
        elif path == "/api/summary":
            try:
                posture = build_posture(PostureStore(), utcnow(), "24h")
            except Exception as error:
                self.log_error("posture summary failed: %r", error)
                posture = None
            self._send(200, "application/json",
                       json.dumps(build_summary(query.latest_topology(), InventoryStore().devices(), posture)))
            return
        elif path == "/triage":
            try:
                store = InventoryStore()
                devices = store.devices()
                body = render_triage_page(store.triage(devices), identify.gather(devices))
            except Exception as error:
                self.log_error("unhandled error in GET %s: %r", path, error)
                self._send(500, "text/plain; charset=utf-8", "Internal error")
                return
        elif path == "/devices":
            try:
                devices = InventoryStore().devices()
                body = render_devices_page(devices, identify.gather(devices))
            except Exception as error:
                self.log_error("unhandled error in GET %s: %r", path, error)
                self._send(500, "text/plain; charset=utf-8", "Internal error")
                return
        elif path == "/coverage":
            try:
                body = render_coverage_page(InventoryStore().coverage())
            except Exception as error:
                self.log_error("unhandled error in GET %s: %r", path, error)
                self._send(500, "text/plain; charset=utf-8", "Internal error")
                return
        elif DEVICE_PAGE.match(path):
            device_id = int(DEVICE_PAGE.match(path).group(1))
            try:
                devices = InventoryStore().devices()
                device = next((d for d in devices if d["id"] == device_id), None)
                if device is None:
                    self._send(404, "text/plain; charset=utf-8", "Not found")
                    return
                ports = (((PostureStore().statuses().get("ports") or {}).get("detail") or {})
                         .get("devices") or {}).get(str(device_id))
                from atlas.wiring import suggest
                suggestion = next((s for s in suggest.current(devices) if s["device_id"] == device_id), None)
                body = render_device_page(device, devices, ports, _latest_wiring(), suggestion)
            except Exception as error:
                self.log_error("unhandled error in GET %s: %r", path, error)
                self._send(500, "text/plain; charset=utf-8", "Internal error")
                return
        elif path.startswith("/api/"):
            try:
                result = api.handle("GET", self.path)
            except Exception as error:
                self.log_error("unhandled error in GET %s: %r", path, error)
                self._send(500, "application/json", json.dumps({"error": "internal error"}))
                return
            if result is None:
                self._send(404, "application/json", json.dumps({"error": "not found"}))
            else:
                self._send(result[0], "application/json", json.dumps(result[1]))
            return
        elif path.startswith("/static/"):
            name = path[len("/static/"):]
            if name not in STATIC_FILES:
                self._send(404, "text/plain; charset=utf-8", "Not found")
                return
            data = (STATIC_DIR / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=86400")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
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

        raw = self.rfile.read(length)

        if self.auth:
            if path in ("/login", "/setup", "/logout"):
                self._auth_form(path, parse_qs(raw.decode("utf-8", "replace")))
                return
            if not self._session_ok():
                self._send(401, "application/json", json.dumps({"error": "sign in first"}))
                return

        try:
            body = json.loads(raw or b"null")
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

    def _beats(self, settings, now):

        from atlas.monitoring.heartbeat import _key, state, token

        if not settings.uptime.heartbeats:
            return []
        statuses, key = PostureStore().statuses(), _key()
        return [(hb, {"state": state(hb, last, now), "at": (last or {}).get("at")}, token(hb.name, key))
                for hb in settings.uptime.heartbeats
                for last in [(statuses.get(f"ping:{hb.name}") or {}).get("detail")]]

    def _ping(self, path):

        from atlas.monitoring.heartbeat import find, ping
        from atlas.posture.store import PostureStore

        parts = path[len("/ping/"):].split("/")
        failed = parts[1:] == ["fail"]
        beat = find(parts[0], load_config().uptime.heartbeats) if len(parts) in (1, 2) and (len(parts) == 1 or failed) \
            else None
        if beat is None:
            self._send(404, "text/plain; charset=utf-8", "no such heartbeat")
            return
        ping(PostureStore(), beat.name, utcnow(), failed=failed)
        self._send(200, "text/plain; charset=utf-8", "ok")

    def _send(self, status, content_type, body):

        encoded = body.encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_server(host="127.0.0.1", port=8420, auth=None):
    """
    Blocks until interrupted (Ctrl+C) - on-demand like every other
    Atlas command, not a background/daemon process; the user starts
    it explicitly in a foreground terminal and stops it the same way.
    auth: an atlas.web.auth.Auth to require sign-in, None when a proxy does it.
    """

    from atlas.web import render

    render.SIGN_OUT = auth is not None
    handler = type("AtlasWebHandler", (AtlasWebHandler,), {"auth": auth}) if auth else AtlasWebHandler
    httpd = ThreadingHTTPServer((host, port), handler)

    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
