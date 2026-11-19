"""
Internet view (lanxang internet check -> Security page, "What the internet sees"): once a day, asks Shodan's
free InternetDB what it last saw on the home's public IP - the one the posture collector already reads - and
alerts on an open port that isn't in posture.expected_ports, or a CVE reported for that IP. Opt-in
(posture.internet_view): it sends the home IP to Shodan. A failed lookup keeps the last answer and the open alerts,
and so does an empty answer (404) after a real one - Shodan dropping its data is not an all-clear. A new public IP
starts from nothing. Setup's Save re-marks the stored ports against the new expected ports without a lookup.
"""

from datetime import datetime, timedelta

import requests

from lanxang.alerts import Text

CHECK_EVERY = timedelta(hours=24)
SOURCE = "internet_view"


def lookup(ip, url, get=requests.get):
    """{"ok": True, "known", "ports", "vulns", "cpes", "hostnames"} or {"ok": False, "error"}; 404 = nothing known."""

    try:
        response = get(url.format(ip=ip), timeout=10)
        if response.status_code == 404:
            return {"ok": True, "known": False, "ports": [], "vulns": [], "cpes": [], "hostnames": []}
        response.raise_for_status()
        data = response.json() or {}
        return {"ok": True, "known": True, "ports": sorted({int(p) for p in data.get("ports") or []}),
                "vulns": sorted(data.get("vulns") or []), "cpes": list(data.get("cpes") or []),
                "hostnames": list(data.get("hostnames") or [])}
    except (requests.RequestException, ValueError, TypeError, AttributeError) as error:
        return {"ok": False, "error": str(error) or type(error).__name__}


def due(detail, ip, now):
    """24 hours since the last check, or the public IP changed since."""

    checked = (detail or {}).get("checked_at")
    return not checked or detail.get("ip") != ip or now - datetime.fromisoformat(checked) >= CHECK_EVERY


def _port_text(port, ip):

    from lanxang.devices.ports import port_label

    return f"**⚠️ Port {port} is open to the internet**\n{port_label(port)} on {ip}, seen by Shodan"


def turn_off(store, now):
    """Switched off: resolve this check's alerts and drop its last answer, once."""

    from lanxang.alerts import report

    if SOURCE in store.statuses():
        report(SOURCE, [], now, store)
        store.clear_status(SOURCE)


def _issues(detail):

    from lanxang.alerts import issue

    ip = detail["ip"]
    return ([issue("internet_port", str(p["port"]), f"Port {p['port']} is open to the internet",
                   _port_text(p["port"], ip).split("\n", 1)[1], href="/posture")
             for p in detail["ports"] if not p["expected"]]
            + [issue("internet_cve", cve, f"{cve} reported on your public IP", f"on {ip}, seen by Shodan",
                     href="/posture") for cve in detail["vulns"]])


def _send(settings, store, texts, now, send):

    from lanxang import notify
    from lanxang.alerts import allowed

    for text in texts:
        if not allowed(store, text, now):
            continue
        if send:
            send(text)
        elif notify.configured(settings.notify):
            notify.send(settings.notify, text)


def run(settings, store, now, *, get=requests.get, send=None, force=False):
    """One daily lookup (skipped inside 24 h on the same IP unless force). Status source 'internet_view'."""

    from lanxang.alerts import report

    config = settings.posture
    if not config.internet_view:
        turn_off(store, now)
        return [], {}
    statuses = store.statuses()
    ip = ((statuses.get("public_ip") or {}).get("detail") or {}).get("ip")
    previous = (statuses.get(SOURCE) or {}).get("detail") or {}
    if not ip or (not force and not due(previous, ip, now)):
        return [], previous
    if previous.get("ip") != ip:                  # a new IP: the old one's answer says nothing about it
        previous = {}

    found = lookup(ip, config.internet_view_url, get)
    if found["ok"] and not found["known"] and previous.get("known"):
        found = {"ok": False, "error": "Shodan has no current data for this IP"}
    detail = {"checked_at": now.isoformat(timespec="minutes"), "ip": ip, "ok": found["ok"],
              "known": previous.get("known"), "ports": previous.get("ports", []),
              "vulns": previous.get("vulns", []), "cpes": previous.get("cpes", []), "error": found.get("error", "")}
    if not found["ok"]:                           # keep the last answer and leave the open alerts alone
        store.set_status(SOURCE, False, detail, now)
        return [], detail

    expected = set(config.expected_ports)
    detail.update(known=found["known"], vulns=found["vulns"], cpes=found["cpes"],
                  ports=[{"port": p, "expected": p in expected} for p in found["ports"]])
    unexpected = [p["port"] for p in detail["ports"] if not p["expected"]]
    alerted = {p["port"] for p in previous.get("ports", []) if not p["expected"]}

    texts = [Text(_port_text(port, ip), f"{SOURCE}:internet_port:{port}") for port in unexpected if port not in alerted]
    texts += [Text(f"**⚠️ {cve} reported on your public IP**", f"{SOURCE}:internet_cve:{cve}")
              for cve in detail["vulns"] if cve not in set(previous.get("vulns", []))]
    texts += [Text(f"**✓ Port {port} no longer seen from the internet**", f"{SOURCE}:internet_port:{port}")
              for port in sorted(alerted - set(found["ports"]))]
    texts += [Text(f"**✓ {cve} no longer reported on your public IP**", f"{SOURCE}:internet_cve:{cve}")
              for cve in previous.get("vulns", []) if cve not in set(detail["vulns"])]

    report(SOURCE, _issues(detail), now, store)
    _send(settings, store, texts, now, send)
    store.set_status(SOURCE, not unexpected and not detail["vulns"], detail, now)

    return texts, detail


def reassess(settings, store, now, *, send=None):
    """Setup's Save: re-mark the stored ports against posture.expected_ports - no lookup, checked_at unchanged."""

    from lanxang.alerts import report

    config = settings.posture
    detail = dict((store.statuses().get(SOURCE) or {}).get("detail") or {})
    if not config.internet_view or not detail.get("ports") and not detail.get("vulns"):
        return [], detail
    expected = set(config.expected_ports)
    was = {p["port"]: p["expected"] for p in detail["ports"]}
    detail["ports"] = [{"port": port, "expected": port in expected} for port in sorted(was)]
    texts = [Text(f"**✓ Port {port} is now expected**", f"{SOURCE}:internet_port:{port}")
             for port, before in was.items() if not before and port in expected]
    texts += [Text(_port_text(port, detail["ip"]), f"{SOURCE}:internet_port:{port}")
              for port, before in was.items() if before and port not in expected]

    report(SOURCE, _issues(detail), now, store)
    _send(settings, store, texts, now, send)
    unexpected = [p for p in detail["ports"] if not p["expected"]]
    store.set_status(SOURCE, detail.get("ok", False) and not unexpected and not detail["vulns"], detail, now)

    return texts, detail
