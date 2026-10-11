"""
One collection pass (atlas access collect, run by atlas-scan every 15 min):
new Traefik access-log lines -> hourly hits + geolocated IPs; new Jellyfin
sign-ins / failed attempts from its activity log; monthly geo DB refresh.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

from atlas.access import geo
from atlas.access.parse import is_private, parse_line, read_new
from atlas.posture.collectors.asn import load_table

FIRST_RUN_BYTES = 20_000_000
JELLYFIN_IP = re.compile(r"IP address:\s*(\S+)")
JELLYFIN_EVENTS = {"AuthenticationSucceeded": True, "SessionStarted": True, "AuthenticationFailed": False}
JELLYFIN_USER = (re.compile(r"^(.+?) successfully authenticated"), re.compile(r"^(.+?) is online from (.+)$"),
                 re.compile(r"^Failed login attempt from (.+)$"))


def jellyfin_logins(entries):
    """Jellyfin /System/ActivityLog/Entries items -> login dicts (only the sign-in event types)."""

    out = []
    for e in entries:
        if e.get("Type") not in JELLYFIN_EVENTS:
            continue
        ip = JELLYFIN_IP.search(e.get("ShortOverview") or "")
        user, client = "", ""
        for pattern in JELLYFIN_USER:
            m = pattern.match(e.get("Name") or "")
            if m:
                user, client = m.group(1), (m.group(2) if m.lastindex and m.lastindex > 1 else "")
                break
        out.append({"app": "jellyfin", "external_id": str(e["Id"]), "time": _jf_time(e["Date"]), "user": user or "?",
                    "ip": ip.group(1) if ip else "", "ok": JELLYFIN_EVENTS[e["Type"]], "client": client})
    return out


def _jf_time(text):
    return datetime.fromisoformat(text[:19])   # "2026-10-10T23:29:51.1234567Z" -> UTC, seconds precision


# Apps whose phone/TV clients sign in through Traefik: the access log has the real IP + HTTP status of the login
# POST; the app's own log (docker timestamps, UTC) names the user. Matched by time.
LOGIN_ROUTES = {"audiobookshelf": ("/login",), "kavita": ("/api/Account/login",)}
APP_USER_LINES = {
    "audiobookshelf": re.compile(r'\[LocalAuth\][^"]*"(?P<user>[^"]+)"'),
    "kavita": re.compile(r"AccountController (?P<user>\S+) (?:attempting to login|logged in)"),
}
MATCH_SECONDS = 5


def app_user_events(app, log_text):
    """`docker logs --timestamps` text -> [(utc time, user)] for that app's sign-in lines."""

    pattern, out = APP_USER_LINES[app], []
    for line in log_text.splitlines():
        stamp, _, rest = line.partition(" ")
        m = pattern.search(rest)
        if m:
            try:
                out.append((datetime.fromisoformat(stamp[:19]), m["user"]))
            except ValueError:
                continue
    return out


def proxied_logins(entries, events_by_app):
    """Login POSTs from the Traefik log -> login dicts, user taken from the nearest app log line (else "?")."""

    out = []
    for e in entries:
        app = e["service"]
        if app not in LOGIN_ROUTES or e["method"] != "POST" or e["path"].split("?")[0] not in LOGIN_ROUTES[app]:
            continue
        near = [(abs((t - e["time"]).total_seconds()), u) for t, u in events_by_app.get(app, [])]
        near = [x for x in near if x[0] <= MATCH_SECONDS]
        out.append({"app": app, "external_id": f"{e['time'].isoformat()}|{e['ip']}", "time": e["time"],
                    "user": min(near)[1] if near else "?", "ip": e["ip"], "ok": 200 <= e["status"] < 300, "client": ""})
    return out


AUTHELIA_LINE = re.compile(r'msg="(?P<kind>Successful|Unsuccessful) (?P<factor>1FA|2FA)[^"]*?by user \'(?P<user>[^\']*)\'".*?'
                           r'remote_ip=(?P<ip>[0-9a-fA-F:.]+)')


def authelia_logins(log_text):
    """`docker logs --timestamps authelia` (log level debug - successes are only logged at debug) -> login dicts."""

    out = []
    for line in log_text.splitlines():
        stamp, _, rest = line.partition(" ")
        m = AUTHELIA_LINE.search(rest)
        if not m:
            continue
        try:
            when = datetime.fromisoformat(stamp[:19])
        except ValueError:
            continue
        out.append({"app": "authelia", "external_id": f"{stamp}|{m['ip']}|{m['factor']}", "time": when,
                    "user": m["user"] or "?", "ip": m["ip"], "ok": m["kind"] == "Successful", "client": m["factor"]})
    return out


class AccessCollector:

    def __init__(self, settings, posture_settings, store, get=requests.get, signal=None, send=None, docker=None):
        self.settings, self.posture, self.store, self.get = settings, posture_settings, store, get
        self.signal, self.send, self.docker = signal, send, docker

    def _app_events(self, since):
        """Sign-in lines from each app container's log since `since` (needs the docker socket; skipped without it)."""

        events = {}
        for app in LOGIN_ROUTES:
            try:
                text = self.docker.containers.get(app).logs(since=since, timestamps=True).decode("utf-8", "replace")
                events[app] = app_user_events(app, text)
            except Exception:
                events[app] = []
        return events
        self._geo, self._asn = None, None

    def _locate(self, ip):
        if is_private(ip):
            return {"country": "Home network", "city": "", "cc": ""}
        info = (self._geo.lookup(ip) if self._geo else None) or {}
        a = self._asn.lookup(ip) if self._asn else None
        if a:
            info.update(asn=a.asn, org=a.org, cc=info.get("cc") or a.cc)
        return info

    def _alert(self):
        """One Signal message (Note to Self via notify.signal) listing sign-ins from places not seen before."""

        pending = self.store.unalerted_reviews()
        if not pending or not self.signal or not self.signal.url:
            return 0
        lines = "\n".join(f"\u2022 **{p['user']}** \u2192 {p['app']} from {p['label']} ({p['ip']})" for p in pending[:10])
        text = (f"\U0001F30D **New sign-in place{'s' if len(pending) > 1 else ''}**\n\n{lines}\n\n"
                "\u2705 Expected? Confirm it on Atlas \u2192 Access.")
        from atlas.devices.notify import send_signal
        ok, _ = (self.send or send_signal)(self.signal, text)
        if ok:
            self.store.mark_alerted([p["id"] for p in pending])
        return len(pending) if ok else 0

    def run(self, now):
        result = {}
        s = self.settings

        try:
            result["geo_refreshed"] = geo.refresh(s.geo_path, now, get=self.get)
        except Exception as error:
            result["geo_error"] = str(error)[:200]
        self._geo = geo.GeoDB(s.geo_path)
        self._asn = load_table(self.posture.asn_path)

        path = Path(s.traefik_log)
        if path.exists():
            offset = int(self.store.get_state("traefik_offset", "-1"))
            if offset < 0:   # first run: seed with roughly the last day, not months of history
                offset = max(0, path.stat().st_size - FIRST_RUN_BYTES)
            lines, offset = read_new(path, offset)
            entries = [e for e in map(parse_line, lines) if e and e["ip"] not in s.ignore_ips]
            self.store.touch_ips(self.store.record_hits(entries), self._locate)
            logins = [e for e in entries if e["service"] in LOGIN_ROUTES and e["method"] == "POST"]
            if logins and self.docker is not None:
                since = min(e["time"] for e in logins) - timedelta(seconds=MATCH_SECONDS)
                found = proxied_logins(logins, self._app_events(since))
                result["app_logins_added"] = self.store.record_logins(found)
            self.store.set_state("traefik_offset", offset)
            result["log_lines"], result["requests"] = len(lines), len(entries)
        else:
            result["log_error"] = f"{path} not found"

        if self.docker is not None:
            try:
                since = self.store.get_state("authelia_since") or (now - timedelta(days=1)).isoformat()
                text = self.docker.containers.get("authelia").logs(since=datetime.fromisoformat(since),
                                                                   timestamps=True).decode("utf-8", "replace")
                result["authelia_logins_added"] = self.store.record_logins(authelia_logins(text))
                self.store.set_state("authelia_since", now.isoformat())
            except Exception as error:
                result["authelia_error"] = str(error)[:200]

        if s.jellyfin_url and s.jellyfin_api_key:
            try:
                r = self.get(s.jellyfin_url.rstrip("/") + "/System/ActivityLog/Entries?limit=200",
                             headers={"Authorization": f'MediaBrowser Token="{s.jellyfin_api_key}"'}, timeout=30)
                r.raise_for_status()
                logins = [l for l in jellyfin_logins(r.json().get("Items", [])) if l["ip"]]
                result["logins_added"] = self.store.record_logins(logins)
                self.store.touch_ips({l["ip"]: l["time"] for l in logins}, self._locate)
            except Exception as error:
                result["jellyfin_error"] = str(error)[:200]

        result["new_places"] = len(self.store.classify_logins(now, s.home_ips))
        result["alerted"] = self._alert()
        result["pruned"] = self.store.prune(now - timedelta(days=s.retention_days))
        return result
