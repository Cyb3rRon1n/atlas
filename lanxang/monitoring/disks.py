"""
Disk health from Proxmox (read by `lanxang proxmox scan`, every 15 minutes in atlas-scan): each disk's SMART result,
how much life an SSD has left, its temperature and its bad-sector count.

  failed     SMART says the disk is failing
  hot        over health.disk_hot_hdd_c / disk_hot_ssd_c at two scans in a row (not one busy moment)
  worn       an SSD with health.disk_life_percent or less life left
  bad sectors  the count went up since the last scan - a disk that already had a few and stays steady is fine

One alert when a problem starts and one when it's gone; growing bad sectors are one message each time.
"""

from lanxang.alerts import Text


def _key(node, disk):
    return f"{node}:{disk.get('serial') or disk.get('dev')}"


def _label(host, disk):
    return f"{host} {disk.get('dev') or '?'}" + (f" ({disk['model']})" if disk.get("model") else "")


def problems(disk, health, was_hot=False):
    """{kind: (title, detail)} for one disk. was_hot: it was already over the limit at the last scan."""

    found = {}
    if disk.get("health") not in ("", "PASSED", "OK", "UNKNOWN", None):
        found["failed"] = ("is failing its SMART check", f"SMART says {disk['health']} - copy what's on it and "
                           "replace it" + (f" (serial {disk['serial']})" if disk.get("serial") else ""))
    limit = health.disk_hot_hdd_c if disk.get("type") == "hdd" else health.disk_hot_ssd_c
    if disk.get("temp") is not None and disk["temp"] >= limit and was_hot:
        found["hot"] = ("is running hot", f"{disk['temp']}°C (limit {limit}°C) - check the fans and airflow")
    if disk.get("life") is not None and disk.get("type") != "hdd" and disk["life"] <= health.disk_life_percent:
        found["worn"] = ("is nearly worn out", f"{disk['life']}% of its life left - plan a replacement")
    elif disk.get("worn"):                                     # the NAS's own "life below its limit" flag
        found["worn"] = ("is nearly worn out", "the NAS says its life left is below the limit - plan a replacement")
    return found


def run(settings, store, now, nodes, host_names=None, *, source="disks", send=None):
    """Check every disk on every node. Status source 'disks' in the posture store; returns the saved detail."""

    from lanxang import notify
    from lanxang.alerts import allowed, issue, report

    health = settings.health
    previous = ((store.statuses().get(source) or {}).get("detail")) or {}
    old = previous.get("disks") or {}
    seen, found, texts = {}, [], []

    for node in nodes:
        host = (host_names or {}).get(node.get("name")) or node.get("name")
        for disk in node.get("disks") or []:
            key = _key(node.get("name"), disk)
            before = old.get(key) or {}
            hot_limit = health.disk_hot_hdd_c if disk.get("type") == "hdd" else health.disk_hot_ssd_c
            now_problems = problems(disk, health, was_hot=(before.get("temp") or 0) >= hot_limit)
            label = _label(host, disk)
            for kind, (title, detail) in now_problems.items():
                found.append(issue(kind, key, f"Disk {label} {title}", detail, href="/?home"))
                if kind not in (before.get("problems") or []):
                    texts.append(Text(f"**💽 Disk {label} {title}**\n• {detail}", f"disks:{kind}:{key}"))
            for kind in set(before.get("problems") or []) - set(now_problems):
                texts.append(Text(f"**✅ Disk {label}: no longer {_PAST[kind]}**", f"disks:{kind}:{key}"))
            if disk.get("bad") is not None and before.get("bad") is not None and disk["bad"] > before["bad"]:
                texts.append(Text(f"**💽 Disk {label}: bad sectors went from {before['bad']} to {disk['bad']}**\n"
                                  "• a disk that keeps adding them is wearing out - check the pool and keep backups "
                                  "current", f"disks:bad:{key}"))
            seen[key] = {"temp": disk.get("temp"), "bad": disk.get("bad"), "problems": sorted(now_problems)}

    report(source, found, now, store)
    for text in texts:
        if allowed(store, text, now):
            if send:
                send(text)
            elif notify.configured(settings.notify):
                notify.send(settings.notify, text)

    detail = {"checked_at": now.isoformat(timespec="seconds"), "disks": seen}
    store.set_status(source, not found, detail, now)
    return detail


_PAST = {"failed": "failing SMART", "hot": "running hot", "worn": "worn out"}
