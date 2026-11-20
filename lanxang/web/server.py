"""
A local HTTP server over Lanxang's existing stored data - no new
dependency, stdlib http.server only, matching this project's
"lightweight" scoping for this feature. The server is read-only except
for the device inventory's /api/* POST routes: those are gated by a
same-origin check, capped at 64 KB of JSON, and write only through
InventoryStore. Sign-in is lanxang.web.auth (web.auth: builtin, the default)
or, with web.auth: proxy, the auth proxy in front of the host.
"""

import json
import os
import re
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, quote, urlsplit

import psutil

from lanxang.config.loader import load_config
from lanxang.web import render as web_render
from lanxang.alerts import AlertStore
from lanxang.devices import identify
from lanxang.devices.store import InventoryStore
from lanxang.discovery.host_health import get_host_health
from lanxang.knowledge.queries import KnowledgeQueries
from lanxang.posture.model import build_posture, build_trends
from lanxang.posture.store import PostureStore
from lanxang.web import api
from lanxang.web.auth import COOKIE, SESSION_SECONDS
from lanxang.web.chat_page import render_chat_page
from lanxang.web.login_page import render_login_page, render_setup_page
from lanxang.web.devices_pages import render_coverage_page, render_device_page, render_devices_page, render_triage_page
from lanxang.web.hosts_page import build_history, render_hosts_summary
from lanxang.access.store import AccessStore
from lanxang.web.access_page import WINDOWS as ACCESS_WINDOWS, render_access_page
from lanxang.web.home_page import (build_hosts, build_storage, build_vitals, day_states, interesting_events, parse_mdstat,
                                 render_home_page, scan_state, setup_steps, since_window, storage_trend)
from lanxang.web.posture_page import render_posture_page
from lanxang.web.graph import build_graph
from lanxang.web.network_page import render_network_page
from lanxang.web.cabling_page import cabling_csv, render_cabling_page
from lanxang.web.render import _posture_block, build_summary, render_history_page, render_overview_page
from lanxang.web.trends_page import MIN_POINTS, WINDOWS as TREND_WINDOWS, render_trends_page
from lanxang.clock import utcnow


MAX_BODY = 65536

DEVICE_PAGE = re.compile(r"^/devices/(\d+)$")

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Explicit allow-list - never build a filesystem path from the request.
STATIC_FILES = {"cytoscape.min.js", "elk.bundled.js", "fonts/Lexend.woff2", "fonts/NotoSansLao-Medium.woff2"}


def _latest_wiring():
    """Latest wiring snapshot, or None when the wired map is off or never ran - a device page never fails over it."""

    try:
        from lanxang.wiring.store import WiringStore
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
    """notify: settings for the Alerts page's quiet hours, or None if the config file can't be read."""

    try:
        return load_config().notify
    except Exception:
        return None

class AtlasWebHandler(BaseHTTPRequestHandler):

    auth = None     # an lanxang.web.auth.Auth when web.auth is builtin; None = an auth proxy guards the host

    def _session_ok(self):

        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
        except Exception:
            return False
        morsel = cookie.get(COOKIE)

        return bool(morsel) and self.auth.valid_session(morsel.value)

    def _viewer_zone(self):
        """The IANA zone the browser reported (lanxang-tz cookie), if it names a real one; else None."""

        from zoneinfo import ZoneInfo
        from urllib.parse import unquote
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
            name = unquote(cookie["lanxang-tz"].value)
            ZoneInfo(name)
        except Exception:
            return None
        return name

    def _seen_cookie(self):
        """The lanxang-seen cookie's value (Home's "Since you were here"), or None."""

        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
            return cookie["lanxang-seen"].value
        except Exception:
            return None

    def _change_sources(self, query):
        """What changes_feed.collect() reads: the same for Activity's What changed and Home's Since you were here."""

        from lanxang.web import changes_feed

        return {"alerts": lambda at, days: AlertStore().listing(at, days), "devices": InventoryStore().devices,
                "changes": lambda since: [(at, kind, payload) for kind in changes_feed.CHANGE_EVENTS
                                          for at, payload in query.events_since([kind], since)]}

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
                self._send(401, "application/json", json.dumps({"error": "Lanxang is not set up yet"}))
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
                error = "Too many attempts — wait a few minutes." if self.auth.limited(client) else "That setup code is not right."
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
                       render_login_page("Too many attempts — wait a few minutes.", next_path))
        elif result is None:
            self.log_message("failed sign-in from %s", client)
            self._send(401, "text/html; charset=utf-8", render_login_page("Wrong password.", next_path))
        else:
            self._redirect(next_path, cookie=result)

    def _host_history(self, query, topology):
        """24 h of host and Proxmox node usage for the Overview meters; {} when there is none (optional data)."""

        try:
            since = utcnow() - timedelta(days=1)
            topology = topology or {}
            pve = (topology.get("proxmox") or {}).get("host")
            lan = {h.get("address"): h["name"] for h in topology.get("lan", [])}
            scans = query.events_since(["atlas.proxmox.scan.completed"], since)
            node_set = {n["name"] for _, p in scans for n in p.get("nodes", [])}
            names = {next(iter(node_set)): lan[pve]} if len(node_set) == 1 and pve in lan else {}    # as /trends
            samples = query.events_since(["atlas.host.sample"], since)

            return build_history(samples, scans, topology.get("host") or "this host", names)
        except Exception as error:
            self.log_error("overview: history failed: %r", error)
            return {}

    def _home_data(self, query, brief=True):
        """
        render_home_page()'s arguments, plus "seen": the lanxang-seen cookie value to write back. Each source is
        fetched on its own so one failing (no posture DB, no Proxmox scan yet) only blanks its own part; a failed part
        the verdict rests on is named in "failed" so Home never calls it healthy. brief=False (/overview) stops at
        hosts, storage and topology: no briefing.
        """

        failed = []

        def safe(label, fetch, part=None):
            try:
                return fetch()
            except Exception as error:
                self.log_error("home: %s failed: %r", label, error)
                if part and part not in failed:
                    failed.append(part)
                return None

        from lanxang.web.home_page import home_display

        now = utcnow()
        viewer_zone = self._viewer_zone()
        display = home_display(viewer_zone)             # days and times in the viewer's zone (time_zone: browser)
        settings = safe("config", load_config)
        health_settings = settings.health if settings else None
        topology = safe("topology", query.latest_topology, "hosts")
        pve_scan = safe("proxmox scan", lambda: query.latest_event_payload("atlas.proxmox.scan.completed"), "hosts")
        host_issues = safe("host issues", lambda: ((PostureStore().statuses().get("host") or {}).get("detail")
                                                    or {}).get("issues"), "hosts")
        local = safe("host health", lambda: get_host_health(health_settings.status_urls if health_settings else None),
                     "hosts")

        def usage():
            return {label: psutil.disk_usage(path) for label, path in (health_settings.storage_paths or {}).items()}

        storage = build_storage(safe("mdstat", lambda: parse_mdstat(Path("/proc/mdstat").read_text())) or [],
                                (safe("storage paths", usage) if health_settings else None) or {},
                                (local or {}).get("status_feeds"), pve_scan, topology, health_settings,
                                safe("nas", lambda: (PostureStore().statuses().get("nas") or {}).get("detail"))
                                if settings and settings.nas.enabled else None)

        hosts = build_hosts(topology, local, pve_scan, host_issues)
        if not brief:
            return dict(hosts=hosts, storage=storage, topology=topology)

        from lanxang.monitoring.uptime import UptimeStore

        posture = safe("posture", lambda: _posture_block(build_posture(PostureStore(), now, "24h")), "posture")
        devices = safe("devices", lambda: InventoryStore().devices())
        checks = settings.uptime.checks if settings else []
        ups = safe("ups", lambda: (PostureStore().statuses().get("ups") or {}).get("detail")) \
            if settings and settings.ups.enabled else None

        last = safe("internet", lambda: UptimeStore().latest("Internet"))
        internet = None
        if last and settings and settings.internet.enabled and now - last[0] < timedelta(minutes=5):
            internet = last[1:]                         # (up, ms); an old result means the check isn't running

        # The briefing: what changed since the last visit, the newest scan, and a week of history for the vitals.
        from lanxang.web import changes_feed

        since, seen = since_window(self._seen_cookie(), now)
        changes = safe("changes", lambda: changes_feed.collect(now, "24h", self._change_sources(query), since=since))
        week = now - timedelta(days=7)
        runs = safe("source runs", lambda: InventoryStore().runs(week))
        last_scan, scans_failing = scan_state(runs)
        try:
            scan_minutes = max(1, int(os.environ.get("LANXANG_SCAN_MINUTES", 15)))
        except ValueError:
            scan_minutes = 15
        fail_after = settings.uptime.fail_after if settings else 2
        internet_days = safe("internet days", lambda: day_states([UptimeStore().history("Internet", week)], fail_after,
                                                                 now, display=display)) if settings and settings.internet.enabled else None
        uptime_days = safe("uptime days", lambda: day_states([UptimeStore().history(c.name, week) for c in checks],
                                                             fail_after, now, display=display)) if checks else None

        def storage_history():
            fresh = now - timedelta(minutes=3 * scan_minutes)
            scans = query.events_since(["atlas.proxmox.scan.completed"], week)
            trend = (storage_trend(scans, fresh_after=fresh)
                     or storage_trend([], query.events_since(["atlas.host.sample"], week), fresh))
            return trend and {**trend, "warn": storage["state"] == "warn"}   # a degraded pool never reads as fine

        vitals = safe("vitals", lambda: build_vitals(runs, internet, internet_days, uptime_days,
                                                     safe("storage history", storage_history), posture, ups))

        ha = safe("homeassistant", lambda: (PostureStore().statuses().get("homeassistant") or {}).get("detail")) \
            if settings and settings.homeassistant.enabled else None
        dns = safe("dns", lambda: (PostureStore().statuses().get("dns") or {}).get("detail")) \
            if settings and settings.dns_filter.enabled else None

        return dict(
            dns=dns, names={d["ip"]: d["name"] for d in devices or [] if d.get("ip")}, ha=ha,
            changes=changes, since=since, vitals=vitals, last_scan=last_scan, scans_failing=scans_failing,
            scan_minutes=scan_minutes, seen=seen,
            viewer_zone=viewer_zone,
            posture=posture, hosts=hosts,
            events=interesting_events(safe("events", lambda: query.recent_events(200)) or []),
            storage=storage, trends=safe("trends", lambda: build_trends(PostureStore(), now, display)),
            analysis=safe("analysis", query.latest_analysis), now=now,
            access_reviews=safe("access reviews", lambda: AccessStore().places("review"), "sign-ins") or [],
            open_alerts=safe("alerts", lambda: AlertStore().listing(now)["open"], "alerts") or [],
            steps=safe("setup steps", lambda: setup_steps(settings, devices or [])) if settings else None,
            failed=failed)

    def do_GET(self):

        path = self.path.split("?", 1)[0]

        if path == "/healthz":
            self._send(200, "text/plain; charset=utf-8", "ok")
            return

        if path.startswith("/ping/"):                  # heartbeats: the token in the address is the password
            self._ping(path)
            return

        if path == "/metrics":                         # Prometheus: signed in, or the API token as a Bearer
            from lanxang.web.metrics import collect, render
            if self.auth and not self._gate(path):
                return
            self._send(200, "text/plain; version=0.0.4; charset=utf-8",
                       render(collect(load_config(), utcnow())))
            return

        if self.auth and not self._gate(path):
            return

        try:                                           # no chat panel while no AI is set up; times as Preferences says
            settings = load_config()
            web_render.AI_ON, web_render.DISPLAY = settings.intelligence.provider != "none", settings.display
        except Exception:
            web_render.AI_ON, web_render.DISPLAY = True, None

        query = KnowledgeQueries()

        if path == "/":
            home = self._home_data(query)
            seen = home.pop("seen")
            self._send(200, "text/html; charset=utf-8", render_home_page(**home), headers=[
                ("Set-Cookie", f"lanxang-seen={seen}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax")])
            return
        elif path == "/posture":
            body = render_posture_page()
        elif path == "/settings":
            from lanxang.web.settings_page import render_settings_page
            body = render_settings_page()
        elif path == "/overview":
            home = self._home_data(query, brief=False)
            body = render_overview_page(query.latest_environment(), query.latest_analysis(),
                                        render_hosts_summary(home["hosts"], home["storage"], home["topology"],
                                                             self._host_history(query, home["topology"])))
        elif path == "/access":
            from datetime import timedelta
            settings = load_config()
            window = (parse_qs(self.path.partition("?")[2]).get("window") or ["7d"])[0]
            window = window if window in ACCESS_WINDOWS else "7d"
            summary = AccessStore().summary(utcnow() - timedelta(days=ACCESS_WINDOWS[window]))
            body = render_access_page(summary, window, settings.access.home_ips, settings.access.enabled,
                                      AccessStore().places())
        elif path == "/alerts":
            from lanxang.web.alerts_page import render_alerts_page
            now = utcnow()
            body = render_alerts_page(AlertStore().listing(now), now, _notify_settings())
        elif path == "/history":
            from lanxang.web import changes_feed
            window = (parse_qs(self.path.partition("?")[2]).get("changes") or ["24h"])[0]
            window = window if window in changes_feed.WINDOWS else "24h"
            events, now = query.recent_events(300), utcnow()
            feed = changes_feed.collect(now, window, self._change_sources(query))
            body = render_history_page(events, changes=changes_feed.render(feed, now, window),
                                       viewer_zone=self._viewer_zone())
        elif path == "/uptime":
            from lanxang.config import local
            from lanxang.monitoring.uptime import UptimeStore
            from lanxang.web.uptime_page import internet_data, render_uptime_page, suggestions
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
            samples = query.events_since(["atlas.host.sample"], since)
            longer = None
            if max(len(samples), len(scans)) < MIN_POINTS:    # too little here: does a longer window have enough?
                for key in [k for k in TREND_WINDOWS if TREND_WINDOWS[k] > TREND_WINDOWS[window]]:
                    start = now - timedelta(days=TREND_WINDOWS[key])
                    if max(len(query.events_since(["atlas.host.sample"], start)),
                           len(query.events_since(["atlas.proxmox.scan.completed"], start))) >= MIN_POINTS:
                        longer = key
                        break
            body = render_trends_page(samples, scans, window, now, topology.get("host") or "this host", names, longer)
        elif path == "/map":
            topology = query.latest_topology()
            body = render_network_page(topology, PostureStore().latest_routes(),
                                       build_graph(InventoryStore().devices(), topology))
        elif path in ("/cabling", "/cabling.csv"):
            from lanxang.wiring.store import WiringStore, diff_snapshots
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
                from lanxang.wiring.cabling import load_cabling
                wiring = load_config().wiring
                # cabling.yaml is read on every view, so a faceplate/label edit shows without a rescan
                from lanxang.wiring import suggest, traffic
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
                from lanxang.web.home_page import home_display
                try:
                    wiring = load_config().wiring
                    setup = {"snmp": wiring.enabled and bool(wiring.switches), "cabling": wiring.enabled}
                except Exception as error:          # the to-do rows that need the config are left out
                    self.log_error("coverage: config failed: %r", error)
                    setup = None
                body = render_coverage_page(InventoryStore().coverage(snapshot=_latest_wiring()), setup,
                                            home_display(self._viewer_zone()))
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
                from lanxang.wiring import suggest
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
            font = name.endswith(".woff2")
            self.send_header("Content-Type", "font/woff2" if font else "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=31536000" if font else "max-age=86400")
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

        from lanxang.monitoring.heartbeat import _key, state, token

        if not settings.uptime.heartbeats:
            return []
        statuses, key = PostureStore().statuses(), _key()
        return [(hb, {"state": state(hb, last, now), "at": (last or {}).get("at")}, token(hb.name, key))
                for hb in settings.uptime.heartbeats
                for last in [(statuses.get(f"ping:{hb.name}") or {}).get("detail")]]

    def _ping(self, path):

        from lanxang.monitoring.heartbeat import find, ping
        from lanxang.posture.store import PostureStore

        parts = path[len("/ping/"):].split("/")
        failed = parts[1:] == ["fail"]
        beat = find(parts[0], load_config().uptime.heartbeats) if len(parts) in (1, 2) and (len(parts) == 1 or failed) \
            else None
        if beat is None:
            self._send(404, "text/plain; charset=utf-8", "no such heartbeat")
            return
        ping(PostureStore(), beat.name, utcnow(), failed=failed)
        self._send(200, "text/plain; charset=utf-8", "ok")

    def _send(self, status, content_type, body, headers=()):

        encoded = body.encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)


def run_server(host="127.0.0.1", port=8420, auth=None):
    """
    Blocks until interrupted (Ctrl+C) - on-demand like every other
    Lanxang command, not a background/daemon process; the user starts
    it explicitly in a foreground terminal and stops it the same way.
    auth: an lanxang.web.auth.Auth to require sign-in, None when a proxy does it.
    """

    from lanxang.web import render

    render.SIGN_OUT = auth is not None
    handler = type("AtlasWebHandler", (AtlasWebHandler,), {"auth": auth}) if auth else AtlasWebHandler
    httpd = ThreadingHTTPServer((host, port), handler)

    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
