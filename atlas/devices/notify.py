"""
Signal alerts through signal-cli-rest-api (POST /v2/send, styled text so
**bold** renders). A failed send leaves the items queued for the next run.
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


def deliver(store, config, now=None):

    if not config.url:
        return []

    errors = []

    for kind, items in store.due_notifications(now).items():

        ok, error = send_signal(config, format_message(kind, items))

        if ok:
            store.mark_sent([item["id"] for item in items], now)
        else:
            errors.append(error)

    return errors
