"""
/metrics: what atlas knows, in Prometheus text format, for Grafana and friends. Read-only, built from what the
checks already saved (nothing is measured on request). A source that isn't set up, or can't be read, is left out.

Access: the usual sign-in, or atlas's read-only API token (the one dashboards like Homepage use) as
`Authorization: Bearer <token>`, so a Prometheus server can scrape without a browser session.
"""

from lanxang.clock import utcnow

HELP = {
    "atlas_uptime_up": ("gauge", "Last uptime check result (1 up, 0 down); includes Internet, Router and DNS"),
    "atlas_uptime_response_ms": ("gauge", "Last uptime check response time in milliseconds"),
    "atlas_devices": ("gauge", "Devices in the inventory by state (known/new/ignored) and status (seen/quiet)"),
    "atlas_alerts_open": ("gauge", "Open alerts by level (problem/watch)"),
    "atlas_disk_temperature_celsius": ("gauge", "Disk temperature"),
    "atlas_disk_healthy": ("gauge", "Disk SMART result (1 passed, 0 failing)"),
    "atlas_disk_life_percent": ("gauge", "SSD life left, percent"),
    "atlas_ups_charge_percent": ("gauge", "UPS battery charge"),
    "atlas_ups_on_battery": ("gauge", "1 while the UPS runs on battery"),
    "atlas_heartbeat_ok": ("gauge", "Heartbeat on time (1), late or failed (0); waiting ones are left out"),
    "atlas_ha_up": ("gauge", "Home Assistant answering (1) or not (0)"),
    "atlas_ha_devices_offline": ("gauge", "Home Assistant devices whose entities are all unavailable"),
    "atlas_ha_low_batteries": ("gauge", "Home Assistant batteries at or under the low mark"),
    "atlas_ha_updates": ("gauge", "Home Assistant updates waiting"),
    "atlas_dns_blocking": ("gauge", "Pi-hole / AdGuard Home ad blocking on (1) or off (0)"),
    "atlas_dns_queries": ("gauge", "DNS queries Pi-hole / AdGuard Home counted (its own window, usually 24 h)"),
    "atlas_dns_blocked": ("gauge", "DNS queries blocked (same window)"),
}


def _label(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _line(name, labels, value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    inside = ",".join(f'{key}="{_label(val)}"' for key, val in labels.items())
    return f"{name}{{{inside}}} {number:g}" if inside else f"{name} {number:g}"


def collect(settings, now, sources=None):
    """{metric name: [(labels, value)]} from the stores. sources: test hook replacing the store reads."""

    from lanxang.monitoring import heartbeat, internet

    sources = sources or _sources()
    found = {name: [] for name in HELP}

    def safely(read):
        try:
            return read()
        except Exception:
            return None

    names = [c.name for c in settings.uptime.checks] + internet.all_names(settings.internet)
    for name in names:
        last = safely(lambda: sources["uptime"](name))
        if last:
            found["atlas_uptime_up"].append(({"check": name}, int(bool(last[1]))))
            found["atlas_uptime_response_ms"].append(({"check": name}, last[2]))

    counts = {}
    for device in safely(sources["devices"]) or []:
        key = (device.get("state"), device.get("status"))
        counts[key] = counts.get(key, 0) + 1
    found["atlas_devices"] = [({"state": s or "", "status": st or ""}, n) for (s, st), n in sorted(counts.items())]

    alerts = safely(sources["alerts"])
    if alerts is not None:                           # unreadable is left out, never reported as 0
        levels = {"problem": 0, "watch": 0}
        for alert in alerts:
            levels[alert.get("level", "problem")] = levels.get(alert.get("level", "problem"), 0) + 1
        found["atlas_alerts_open"] = [({"level": level}, n) for level, n in levels.items()]

    statuses = safely(sources["statuses"]) or {}
    for host, disks in safely(lambda: sources["disks"](statuses)) or []:
        for disk in disks:
            labels = {"host": host, "disk": disk.get("dev") or "", "model": disk.get("model") or ""}
            found["atlas_disk_temperature_celsius"].append((labels, disk.get("temp")))
            if disk.get("health"):
                found["atlas_disk_healthy"].append((labels, int(disk["health"] in ("PASSED", "OK"))))
            found["atlas_disk_life_percent"].append((labels, disk.get("life")))

    for name, ups in (((statuses.get("ups") or {}).get("detail") or {}).get("upses") or {}).items():
        found["atlas_ups_charge_percent"].append(({"ups": name}, ups.get("charge")))
        found["atlas_ups_on_battery"].append(({"ups": name}, int(ups.get("state") in ("battery", "low"))))

    for name, beat in (((statuses.get("heartbeats") or {}).get("detail")) or {}).items():
        if beat.get("state") in ("ok", "late", "failed"):
            found["atlas_heartbeat_ok"].append(({"name": name}, int(beat["state"] == "ok")))

    home = ((statuses.get("homeassistant") or {}).get("detail")) or {}
    if home and settings.homeassistant.enabled:
        info = home.get("info") or {}
        found["atlas_ha_up"].append(({}, int(not home.get("error"))))
        if info:
            found["atlas_ha_devices_offline"].append(({}, len(info.get("offline") or [])))
            found["atlas_ha_low_batteries"].append(({}, len(info.get("batteries") or [])))
            found["atlas_ha_updates"].append(({}, len(info.get("updates") or [])))

    dns = (((statuses.get("dns") or {}).get("detail")) or {}).get("info") or {}
    if dns and settings.dns_filter.enabled:
        found["atlas_dns_blocking"].append(({"server": dns.get("kind", "")}, int(bool(dns.get("blocking")))))
        found["atlas_dns_queries"].append(({"server": dns.get("kind", "")}, dns.get("queries")))
        found["atlas_dns_blocked"].append(({"server": dns.get("kind", "")}, dns.get("blocked")))

    return found


def _sources():

    from lanxang.alerts import AlertStore
    from lanxang.devices.store import InventoryStore
    from lanxang.knowledge.queries import KnowledgeQueries
    from lanxang.monitoring.uptime import UptimeStore
    from lanxang.posture.store import PostureStore

    uptime, alerts = UptimeStore(), AlertStore()

    def disks(statuses):
        scan = KnowledgeQueries().latest_event_payload("lanxang.proxmox.scan.completed") or {}
        found = [(node.get("name"), node.get("disks") or []) for node in scan.get("nodes") or []]
        nas = (statuses.get("nas") or {}).get("detail") or {}
        if nas.get("name"):
            found.append((nas["name"], (nas.get("info") or {}).get("disks") or []))
        return found

    def live_alerts():
        from datetime import datetime
        listing = alerts.listing(utcnow())
        return listing["open"] + listing["watch"]

    return {"uptime": uptime.latest, "devices": InventoryStore().devices, "alerts": live_alerts,
            "statuses": PostureStore().statuses, "disks": disks}


def render(found):
    """Prometheus text exposition format."""

    out = []
    for name, rows in found.items():
        lines = [line for line in (_line(name, labels, value) for labels, value in rows) if line]
        if lines:
            kind, text = HELP[name]
            out += [f"# HELP {name} {text}", f"# TYPE {name} {kind}"] + lines
    return "\n".join(out) + "\n"

