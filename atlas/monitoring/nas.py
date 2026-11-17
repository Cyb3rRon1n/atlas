"""
NAS health from TrueNAS or Synology, read with every `atlas scan` (and `atlas nas check`): pool or volume
health and how full it is, and each disk's health and temperature. Read-only.

  TrueNAS   JSON-RPC over a websocket (wss://<nas>/api/current; its REST API goes away in TrueNAS 26) with an
            API key: pool.query, disk.query, disk.temperatures, and alert.list for SMART warnings. https only:
            TrueNAS revokes a key that was sent without encryption.
  Synology  DSM's web API with an administrator account (DSM only lets admins read storage; that account can be
            denied every folder and app): SYNO.API.Auth login, SYNO.Storage.CGI.Storage load_info, logout.

Not checked against real hardware yet - built from the vendors' API docs and Home Assistant's Synology library.
Disks then go through atlas.monitoring.disks like the Proxmox ones (failing, hot, worn out); a pool that isn't
healthy is one alert, and one more when it is again.
"""

import json
import os
import ssl
from urllib.parse import urlparse

from atlas.alerts import Text

PASSWORD_ENV = "ATLAS_NAS_PASSWORD"            # the TrueNAS API key, or the Synology password
HEALTHY_POOL = ("ONLINE", "NORMAL")


class NasError(Exception):

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


# --- TrueNAS

class _Rpc:
    """JSON-RPC 2.0 calls over one open websocket."""

    def __init__(self, ws):
        self.ws, self.id = ws, 0

    def __call__(self, method, params=()):
        self.id += 1
        self.ws.send(json.dumps({"jsonrpc": "2.0", "id": self.id, "method": method, "params": list(params)}))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get("id") == self.id:                     # anything else is a notification - skip it
                break
        if "error" in reply:
            error = reply["error"] or {}
            reason = ((error.get("data") or {}).get("reason") if isinstance(error.get("data"), dict) else None)
            raise NasError(f"TrueNAS {method}: {reason or error.get('message') or error}", error.get("code"))
        return reply.get("result")


def _truenas_login(call, user, key):

    if user:                                                   # TrueNAS 25.04+: the newer login
        try:
            reply = call("auth.login_ex", [{"mechanism": "API_KEY_PLAIN", "username": user, "api_key": key}])
            if (reply or {}).get("response_type") != "SUCCESS":
                raise NasError("TrueNAS sign-in: API key not accepted")
            return
        except NasError as error:
            if error.code != -32601:                    # anything but "no such method" (24.10)
                raise
    if call("auth.login_with_api_key", [key]) is not True:     # returns False on a bad key, doesn't raise
        raise NasError("TrueNAS sign-in: API key not accepted")


def _truenas(base, user, key, timeout, verify, connect=None):

    if not base.startswith("https://"):
        raise NasError("Use https:// for TrueNAS - it revokes an API key sent without encryption")
    if not key:
        raise NasError(f"Add the TrueNAS API key (the {PASSWORD_ENV} secret)")
    import websocket
    url = "wss://" + base[len("https://"):] + "/api/current"
    ws = (connect or websocket.create_connection)(
        url, timeout=timeout, sslopt=None if verify else {"cert_reqs": ssl.CERT_NONE, "check_hostname": False})
    try:
        call = _Rpc(ws)
        _truenas_login(call, user, key)
        pools = call("pool.query") or []
        disks = call("disk.query") or []
        names = [d.get("name") for d in disks if d.get("name")]
        try:
            temps = call("disk.temperatures", [names]) or {}
        except NasError:
            temps = {}
        try:
            alerts = [a for a in call("alert.list") or [] if not a.get("dismissed") and a.get("level") != "INFO"
                      and "smart" in str(a.get("klass", "")).lower()]
        except NasError:
            alerts = []
    finally:
        try:
            ws.close()
        except Exception:
            pass

    def failing(name):
        return any(name and name in json.dumps([a.get("args"), a.get("formatted"), a.get("text")]) for a in alerts)

    return {
        "kind": "TrueNAS",
        "pools": [{"name": p.get("name"), "health": str(p.get("status") or "").upper(), "size": p.get("size"),
                   "alloc": p.get("allocated")} for p in pools],
        "disks": [{"dev": d.get("name"), "type": _disk_type(d.get("type"), d.get("name")), "size": d.get("size"),
                   "model": d.get("model") or "", "serial": d.get("serial") or "",
                   "health": "FAILED" if failing(d.get("name")) else "PASSED", "life": None,
                   "temp": temps.get(d.get("name")) if isinstance(temps.get(d.get("name")), int) else None,
                   "bad": None} for d in disks]}


def _disk_type(kind, name=""):

    kind = str(kind or "").lower()
    if "nvme" in kind or str(name or "").startswith("nvme"):
        return "nvme"
    return "ssd" if "ssd" in kind else "hdd" if kind else ""


# --- Synology

SYNOLOGY_ERRORS = {400: "wrong account or password", 401: "the account is disabled",
                   402: "permission denied - the account must be an administrator",
                   403: "two-factor is on for this account - use an account without it",
                   404: "two-factor code failed", 406: "two-factor is required for this account",
                   105: "permission denied - the account must be an administrator", 119: "the session expired"}


def _synology(http, base, user, password, timeout, verify):

    def call(what, **params):
        response = http.post(f"{base}/webapi/entry.cgi", data=params, timeout=timeout, verify=verify)
        if response.status_code >= 400:
            raise NasError(f"Synology {what}: HTTP {response.status_code}")
        try:
            reply = response.json()
        except ValueError:
            raise NasError(f"Synology {what}: not a JSON answer - is this the DSM address (port 5001)?")
        if not reply.get("success"):
            code = (reply.get("error") or {}).get("code")
            raise NasError(f"Synology {what}: {SYNOLOGY_ERRORS.get(code, f'error {code}')}")
        return reply.get("data") or {}

    if not user or not password:
        raise NasError(f"Add the Synology account and its password (the {PASSWORD_ENV} secret)")
    sid = call("sign-in", api="SYNO.API.Auth", version="6", method="login", account=user, passwd=password,
               session="atlas", format="sid").get("sid")
    try:
        info = call("storage", api="SYNO.Storage.CGI.Storage", version="1", method="load_info", _sid=sid)
    finally:
        try:
            http.post(f"{base}/webapi/entry.cgi", data={"api": "SYNO.API.Auth", "version": "6", "method": "logout",
                                                         "session": "atlas", "_sid": sid},
                      timeout=timeout, verify=verify)
        except Exception:
            pass

    def number(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def health(d):
        if d.get("smart_status") == "failing" or d.get("status") in ("failing", "crashed", "critical"):
            return "FAILED"
        return "BAD SECTORS" if d.get("exceed_bad_sector_thr") else "PASSED"

    volumes = info.get("volumes") or []
    return {
        "kind": "Synology",
        "pools": [{"name": (v.get("id") or "volume").replace("_", " "), "health": str(v.get("status") or "").upper(),
                   "size": number((v.get("size") or {}).get("total")),
                   "alloc": number((v.get("size") or {}).get("used"))} for v in volumes],
        "disks": [{"dev": d.get("name") or d.get("id"), "type": _disk_type(d.get("diskType"), d.get("device")),
                   "size": number(d.get("size_total")), "model": (d.get("model") or "").strip(),
                   "serial": d.get("serial") or "", "health": health(d),
                   "life": number(d.get("remain_life")) if isinstance(d.get("remain_life"), (int, str)) else None,
                   "worn": bool(d.get("below_remain_life_thr")), "temp": number(d.get("temp")), "bad": None}
                  for d in info.get("disks") or []]}


def fetch(config, environ=None, http=None, connect=None):
    """{"kind", "pools": [{name, health, size, alloc}], "disks": [...as Proxmox's]}. Raises NasError in words a
    person can act on."""

    import requests

    environ = os.environ if environ is None else environ
    base = (config.url or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise NasError("Enter the web address, like https://192.168.1.20 (Synology: https://192.168.1.20:5001)")
    secret = environ.get(PASSWORD_ENV, "")
    try:
        if config.kind == "synology":
            return _synology(http or requests, base, config.user, secret, config.timeout, config.verify_ssl)
        return _truenas(base, config.user, secret, config.timeout, config.verify_ssl, connect)
    except NasError:
        raise
    except Exception as error:                                    # refused, timeout, TLS, bad handshake...
        raise NasError(f"No answer from {base}: {type(error).__name__}") from error


def name(config):

    return config.name or urlparse(config.url or "").hostname or ("Synology" if config.kind == "synology"
                                                                   else "TrueNAS")


def run(settings, store, now, *, get=fetch, send=None):
    """One read: status "nas" on the posture store, pool alerts here, disk alerts via atlas.monitoring.disks."""

    from atlas import notify
    from atlas.alerts import allowed, issue, report
    from atlas.monitoring import disks

    config = settings.nas
    if not config.enabled:
        report("nas", [], now, store)
        return None
    previous = ((store.statuses().get("nas") or {}).get("detail")) or {}
    host = name(config)
    try:
        info, error = get(config), ""
    except NasError as failure:
        info, error = dict(previous.get("info") or {}), str(failure)

    found, texts = [], []
    was_bad = set(previous.get("bad_pools") or [])
    bad = set()
    if error:
        found.append(issue("read", host, f"Can't read the NAS {host}", error, "watch", "/settings#nas"))
        bad = was_bad                                  # can't tell: keep what we knew, say nothing new
    else:
        for pool in info.get("pools") or []:
            if pool.get("health") not in HEALTHY_POOL:
                bad.add(pool["name"])
                found.append(issue("pool", f"{host}:{pool['name']}", f"{host} {pool['name']} is {pool['health']}",
                                   "a disk may have dropped out - check the NAS", href="/"))
                if pool["name"] not in was_bad:
                    texts.append(Text(f"**💽 {host}: {pool['name']} is {pool['health']}**\n• a disk may have dropped "
                                      "out or failed - check the NAS and keep your backups current",
                                      f"nas:pool:{host}:{pool['name']}"))
        for pool in sorted(was_bad - bad):
            texts.append(Text(f"**✅ {host}: {pool} is healthy again**", f"nas:pool:{host}:{pool}"))
    report("nas", found, now, store)

    for text in texts:
        if allowed(store, text, now):
            if send:
                send(text)
            elif notify.configured(settings.notify):
                notify.send(settings.notify, text)
    if not error:                                      # the pool alert first, then which disk
        disks.run(settings, store, now, [{"name": host, "disks": info.get("disks") or []}], source="nas-disks",
                  send=send)

    detail = {"checked_at": now.isoformat(timespec="seconds"), "error": error, "name": host, "info": info,
              "bad_pools": sorted(bad)}
    store.set_status("nas", not found, detail, now)
    return detail
