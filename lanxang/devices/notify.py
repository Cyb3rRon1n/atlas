"""
Device alerts (new / important-offline) and the Signal sender. deliver()
sends through lanxang.notify, so every configured channel gets them; a failed
send leaves the items queued for the next run.
"""

import json
import urllib.request

from lanxang.clock import parse, stamp


def _seen(value, display):

    moment = parse(value) if value else None
    return stamp(moment, display) if moment else value or "never"


def _line(item):

    where = f" ({item['ip']})" if item.get("ip") and item["ip"] != item["device"] else ""
    behind = item.get("behind") or []
    if behind:
        shown = ", ".join(behind[:5]) + (f" +{len(behind) - 5} more" if len(behind) > 5 else "")
        where += f" and {len(behind)} device{'s' * (len(behind) != 1)} behind it ({shown})"

    return f"• {item['device']}{where}"


def _named(names, ids):

    return [names.get(device_id, "?") for device_id in ids]


def format_message(kind, items, display=None):

    if kind == "offline":
        if len(items) == 1 and items[0].get("behind"):
            lines = [f"**🔴 {items[0]['device']} is offline - everything behind it is unreachable**"]
        else:
            lines = ["**🔴 Important device offline**" if len(items) == 1 else f"**🔴 {len(items)} important devices offline**"]
        lines += [_line(item) + (f" - last seen {_seen(item['last_seen'], display)}" if item.get("last_seen") else "")
                  for item in items]
        return "\n".join(lines)

    lines = ["**🆕 New device on the network**" if len(items) == 1 else f"**🆕 {len(items)} new devices on the network**"]
    lines += [_line(item) for item in items]
    lines += ["", "Triage them in atlas."]

    return "\n".join(lines)


def send_signal(config, text):

    body = json.dumps({"message": text, "number": config.number,
                       "recipients": config.recipients, "text_mode": "styled"}).encode()
    request = urllib.request.Request(config.url.rstrip("/") + "/v2/send", data=body,
                                     headers={"Content-Type": "application/json"})

    try:
        urllib.request.urlopen(request, timeout=15)
        return True, ""

    except (OSError, ValueError) as error:
        return False, str(error)


def report_alerts(store, devices, now, snaps=None, display=None):
    """The Alerts page's view of the inventory: important devices offline (folded under the switch, AP or
    gateway they sit behind when that is offline too), devices waiting for a name."""

    from lanxang.alerts import issue, report
    from lanxang.alerts.outages import outages, snapshots

    groups = outages(snapshots() if snaps is None else snaps, devices)
    by_id = {device["id"]: device for device in devices}
    names = {device["id"]: device["name"] for device in devices}
    folded = {device_id for behind in groups.values() for device_id in behind} | set(groups)

    def last_seen(device):
        return (f"last seen {_seen(device['last_seen'], display)}"
                + (f" ({device['ip']})" if device.get("ip") else ""))

    found = [issue("offline", device["id"], f"{device['name']} is offline", last_seen(device),
                   href=f"/devices/{device['id']}", device_id=device["id"])
             for device in devices if device["important"] and device["status"] == "quiet"
             and device["state"] != "ignored" and device["id"] not in folded]
    for box, behind in groups.items():
        if not (by_id[box]["important"] or any(by_id[device_id]["important"] for device_id in behind)):
            continue
        shown = _named(names, behind)
        found.append(issue("offline", box, f"{names[box]} is offline - {len(behind)} device"
                           f"{'s' * (len(behind) != 1)} behind it unreachable",
                           f"{last_seen(by_id[box])}. Behind it: {', '.join(shown[:8])}"
                           + (f" +{len(shown) - 8} more" if len(shown) > 8 else ""),
                           href=f"/devices/{box}", device_id=box))
    new = sum(device["state"] == "new" for device in devices)
    if new:
        found.append(issue("new", "devices", f"{new} new device{'s' * (new != 1)} waiting for a name",
                           "Name them, or mark them known or ignored", "watch", "/devices"))
    report("devices", found, now, store)


def _fold(items, store, snaps):
    """Offline items behind a down switch/AP/gateway become one item for that box; the rest pass through.
    Returns [(item to show, ids it covers, device_id to check mutes against)]."""

    try:
        from lanxang.alerts.outages import outages, snapshots
        devices = store.devices()
        groups = outages(snapshots() if snaps is None else snaps, devices)
    except Exception:                               # no map / stand-in store: one line per device as before
        groups, devices = {}, []
    names = {device["id"]: device for device in devices}
    owner = {device_id: box for box, behind in groups.items() for device_id in behind + [box]}
    out, boxes = [], {}
    for item in items:
        box = owner.get(item.get("device_id"))
        if box is None:
            out.append((item, [item["id"]], item.get("device_id")))
            continue
        if box not in boxes:
            device = names[box]
            boxes[box] = ({"device": device["name"], "ip": device.get("ip"), "last_seen": device.get("last_seen"),
                           "behind": [names[device_id]["name"] for device_id in groups[box]]}, [], box)
            out.append(boxes[box])
        boxes[box][1].append(item["id"])

    return out


def deliver(store, config, now=None, snaps=None, display=None):
    """config is the whole notify: section (NotifyConfig); display: how times read (DisplayConfig)."""

    from lanxang import notify

    if not notify.configured(config):
        return []

    errors = []

    from lanxang.alerts import Text, allowed

    for kind, items in store.due_notifications(now).items():

        rows = _fold(items, store, snaps) if kind == "offline" else [(item, [item["id"]], None) for item in items]
        held = [row for row in rows if not allowed(store, Text("", f"devices:offline:{row[2]}" if kind == "offline"
                                                               else "", row[2]), now)]
        if held:                                    # muted / paused: on the Alerts page, not sent
            store.mark_sent([note for row in held for note in row[1]], now)
            rows = [row for row in rows if row not in held]
            if not rows:
                continue

        ok, error = notify.send(config, format_message(kind, [row[0] for row in rows], display))

        if ok:
            store.mark_sent([note for row in rows for note in row[1]], now)
        else:
            errors.append(error)

    return errors
