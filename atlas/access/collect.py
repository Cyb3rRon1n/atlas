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


class AccessCollector:

    def __init__(self, settings, posture_settings, store, get=requests.get):
        self.settings, self.posture, self.store, self.get = settings, posture_settings, store, get
        self._geo, self._asn = None, None

    def _locate(self, ip):
        if is_private(ip):
            return {"country": "Home network", "city": "", "cc": ""}
        info = (self._geo.lookup(ip) if self._geo else None) or {}
        a = self._asn.lookup(ip) if self._asn else None
        if a:
            info.update(asn=a.asn, org=a.org, cc=info.get("cc") or a.cc)
        return info

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
            self.store.set_state("traefik_offset", offset)
            result["log_lines"], result["requests"] = len(lines), len(entries)
        else:
            result["log_error"] = f"{path} not found"

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

        result["pruned"] = self.store.prune(now - timedelta(days=s.retention_days))
        return result
