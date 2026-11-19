"""
Internet view (lanxang internet check -> Security page, "What the internet sees"): once a day, asks Shodan's
free InternetDB what it last saw on the home's public IP - the one the posture collector already reads - and
alerts on an open port that isn't in posture.expected_ports, or a CVE reported for that IP. Opt-in
(posture.internet_view): it sends the home IP to Shodan. A failed lookup keeps the last answer and the open alerts.
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


def run(settings, store, now, *, get=requests.get, send=None, force=False):
    """One daily lookup (skipped inside 24 h on the same IP unless force). Status source 'internet_view'."""

    from lanxang import notify
    from lanxang.alerts import allowed, issue, report

    config = settings.posture
    if not config.internet_view:
        return [], {}
    statuses = store.statuses()
    ip = ((statuses.get("public_ip") or {}).get("detail") or {}).get("ip")
    previous = (statuses.get(SOURCE) or {}).get("detail") or {}
    if not ip or (not force and not due(previous, ip, now)):
        return [], previous

    found = lookup(ip, config.internet_view_url, get)
    detail = {"checked_at": now.isoformat(timespec="minutes"), "ip": ip, "ok": found["ok"],
              "known": previous.get("known", False), "ports": previous.get("ports", []),
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

    report(SOURCE, [issue("internet_port", str(port), f"Port {port} is open to the internet",
                          _port_text(port, ip).split("\n", 1)[1], href="/posture") for port in unexpected]
           + [issue("internet_cve", cve, f"{cve} reported on your public IP", f"on {ip}, seen by Shodan",
                    href="/posture") for cve in detail["vulns"]], now, store)
    for text in texts:
        if not allowed(store, text, now):
            continue
        if send:
            send(text)
        elif notify.configured(settings.notify):
            notify.send(settings.notify, text)
    store.set_status(SOURCE, not unexpected and not detail["vulns"], detail, now)

    return texts, detail
