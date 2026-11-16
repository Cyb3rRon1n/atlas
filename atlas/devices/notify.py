"""
Device alerts (new / important-offline) and the Signal sender. deliver()
sends through atlas.notify, so every configured channel gets them; a failed
send leaves the items queued for the next run.
"""

import json
import urllib.request


def _line(item):

    where = f" ({item['ip']})" if item.get("ip") and item["ip"] != item["device"] else ""

    return f"• {item['device']}{where}"


def format_message(kind, items):

    if kind == "offline":
        lines = ["**🔴 Important device offline**" if len(items) == 1 else f"**🔴 {len(items)} important devices offline**"]
        lines += [_line(item) + (f" - last seen {item['last_seen'][:16].replace('T', ' ')}" if item.get("last_seen") else "")
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


def report_alerts(store, devices, now):
    """The Alerts page's view of the inventory: important devices offline, devices waiting for a name."""

    from atlas.alerts import issue, report

    found = [issue("offline", device["id"], f"{device['name']} is offline",
                   f"last seen {(device['last_seen'] or 'never')[:16].replace('T', ' ')}"
                   + (f" ({device['ip']})" if device.get("ip") else ""), href=f"/devices/{device['id']}",
                   device_id=device["id"])
             for device in devices if device["important"] and device["status"] == "quiet" and device["state"] != "ignored"]
    new = sum(device["state"] == "new" for device in devices)
    if new:
        found.append(issue("new", "devices", f"{new} new device{'s' * (new != 1)} waiting for a name",
                           "Name them, or mark them known or ignored", "watch", "/devices"))
    report("devices", found, now, store)


def deliver(store, config, now=None):
    """config is the whole notify: section (NotifyConfig)."""

    from atlas import notify

    if not notify.configured(config):
        return []

    errors = []

    from atlas.alerts import Text, allowed

    for kind, items in store.due_notifications(now).items():

        held = [item for item in items if not allowed(store, Text("", f"devices:offline:{item.get('device_id')}"
                                                                  if kind == "offline" else "", item.get("device_id")
                                                                  if kind == "offline" else None), now)]
        if held:                                    # muted / paused: on the Alerts page, not sent
            store.mark_sent([item["id"] for item in held], now)
            items = [item for item in items if item not in held]
            if not items:
                continue

        ok, error = notify.send(config, format_message(kind, items))

        if ok:
            store.mark_sent([item["id"] for item in items], now)
        else:
            errors.append(error)

    return errors
