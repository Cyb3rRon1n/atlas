"""
Home Assistant, read with every `lanxang scan` (and `lanxang ha check`) through its REST API with a long-lived access
token: is HA up, which smart devices it has lost, which batteries are low, which updates wait. Read-only.

  offline   a device whose sensors, cameras, locks, switches, lights... (WATCHED) are all "unavailable" for at
            least homeassistant.offline_hours. TVs, media players, remotes, phones and buttons are left out:
            they go unavailable whenever they're switched off.
  battery   a battery sensor at homeassistant.battery_percent or lower, or a battery-low binary sensor that's on.
  updates   HA's own update entities that are on - listed to watch, never messaged.

One alert when HA stops answering (two checks in a row), when a device goes offline or a battery runs low, and one
when each is fine again.
"""

import json
import os
from datetime import datetime, timezone

from lanxang.alerts import Text

TOKEN_ENV = "LANXANG_HA_TOKEN"
WATCHED = ("sensor", "binary_sensor", "camera", "lock", "climate", "alarm_control_panel", "cover", "switch",
           "light", "fan", "vacuum", "water_heater", "siren", "valve", "humidifier", "lawn_mower")
# one template call: each watched or battery entity's device name (HA's REST API has no device list)
DEVICES_TEMPLATE = ("{% set ns = namespace(r={}) %}{% for s in states if s.domain in " + json.dumps(list(WATCHED))
                    + " %}{% set ns.r = dict(ns.r, **{s.entity_id: device_attr(s.entity_id, 'name_by_user') or "
                    "device_attr(s.entity_id, 'name') or ''}) %}{% endfor %}{{ ns.r | tojson }}")


class HomeAssistantError(Exception):
    pass


def _json(response, what):

    if response.status_code in (401, 403):
        raise HomeAssistantError(f"{what}: the token was refused (HTTP {response.status_code}) - make a new "
                                 "long-lived access token")
    if response.status_code >= 400:
        raise HomeAssistantError(f"{what}: HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError:
        raise HomeAssistantError(f"{what}: not a JSON answer - is this Home Assistant's address?")


def _age_hours(changed, now):

    try:
        when = datetime.fromisoformat(str(changed).replace("Z", "+00:00"))
    except ValueError:
        return 0
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now.replace(tzinfo=timezone.utc) - when).total_seconds() / 3600


def summarize(states, devices, config, now):
    """{"offline": [{name, hours, kinds}], "batteries": [{name, level}], "updates": [{title, installed, latest}]}
    from /api/states and the entity -> device name map."""

    groups = {}
    for entity in states:
        domain = entity["entity_id"].split(".")[0]
        if domain not in WATCHED:
            continue
        attributes = entity.get("attributes") or {}
        name = devices.get(entity["entity_id"]) or attributes.get("friendly_name") or entity["entity_id"]
        group = groups.setdefault(name, {"down": True, "hours": None, "kinds": set()})
        if entity.get("state") != "unavailable":
            group["down"] = False
            continue
        hours = _age_hours(entity.get("last_changed"), now)
        group["hours"] = hours if group["hours"] is None else min(group["hours"], hours)
        group["kinds"].add(domain.replace("_", " "))
    offline = sorted(({"name": name, "hours": round(g["hours"]), "kinds": sorted(g["kinds"])}
                      for name, g in groups.items() if g["down"] and g["hours"] is not None
                      and g["hours"] >= config.offline_hours), key=lambda d: -d["hours"])

    batteries = []
    for entity in states:
        attributes = entity.get("attributes") or {}
        if attributes.get("device_class") != "battery":
            continue
        name = devices.get(entity["entity_id"]) or attributes.get("friendly_name") or entity["entity_id"]
        if entity["entity_id"].startswith("sensor.") and attributes.get("unit_of_measurement") == "%":
            try:
                level = float(entity["state"])
            except (TypeError, ValueError):
                continue
            if level <= config.battery_percent:
                batteries.append({"name": name, "level": round(level)})
        elif entity["entity_id"].startswith("binary_sensor.") and entity.get("state") == "on":
            batteries.append({"name": name, "level": None})

    updates = [{"title": (e.get("attributes") or {}).get("title") or (e.get("attributes") or {}).get("friendly_name")
                or e["entity_id"], "installed": (e.get("attributes") or {}).get("installed_version"),
                "latest": (e.get("attributes") or {}).get("latest_version")}
               for e in states if e["entity_id"].startswith("update.") and e.get("state") == "on"]

    return {"offline": offline, "batteries": batteries, "updates": updates}


def fetch(config, environ=None, http=None, now=None):
    """{"version", "offline", "batteries", "updates"}. Raises HomeAssistantError in words a person can act on."""

    import requests

    from lanxang.clock import utcnow

    http = http or requests
    environ = os.environ if environ is None else environ
    base = (config.url or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise HomeAssistantError("Enter Home Assistant's address, like http://homeassistant.local:8123")
    token = environ.get(TOKEN_ENV, "")
    if not token:
        raise HomeAssistantError(f"Add a long-lived access token (the {TOKEN_ENV} secret)")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        about = _json(http.get(f"{base}/api/config", headers=headers, timeout=config.timeout,
                               verify=config.verify_ssl), "Home Assistant")
        states = _json(http.get(f"{base}/api/states", headers=headers, timeout=config.timeout,
                                verify=config.verify_ssl), "Home Assistant states")
        try:
            reply = http.post(f"{base}/api/template", headers=headers, json={"template": DEVICES_TEMPLATE},
                              timeout=config.timeout, verify=config.verify_ssl)
            devices = json.loads(reply.text) if reply.status_code < 400 else {}
        except (ValueError, TypeError):
            devices = {}                              # device names are a nicety: entity names still work
    except HomeAssistantError:
        raise
    except Exception as error:
        raise HomeAssistantError(f"No answer from {base}: {type(error).__name__}") from error
    return {"version": about.get("version"), **summarize(states, devices if isinstance(devices, dict) else {},
                                                          config, now or utcnow())}


def run(settings, store, now, *, get=fetch, send=None):
    """One read: status "homeassistant" on the posture store, alerts. Returns the saved detail."""

    from lanxang import notify
    from lanxang.alerts import allowed, issue, report

    config = settings.homeassistant
    if not config.enabled:
        report("homeassistant", [], now, store)
        return None
    previous = ((store.statuses().get("homeassistant") or {}).get("detail")) or {}
    try:
        info, error = get(config), ""
        failures = 0
    except HomeAssistantError as failure:
        info, error = dict(previous.get("info") or {}), str(failure)
        failures = previous.get("failures", 0) + 1

    found, texts = [], []
    was_down = previous.get("failures", 0) >= 2
    if failures >= 2:
        found.append(issue("down", "Home Assistant", "Home Assistant isn't answering", error, href="/settings#homeassistant"))
        if not was_down:
            texts.append(Text(f"**🏠 Home Assistant isn't answering**\n• {error}\n• automations and the app may "
                              "not work - check the Home Assistant machine", "ha:down"))
    elif error:
        found.append(issue("read", "Home Assistant", "Can't read Home Assistant", error, "watch",
                           "/settings#homeassistant"))
    elif was_down:
        texts.append(Text("**✅ Home Assistant is answering again**", "ha:down"))

    old_offline = set(previous.get("offline_names") or [])
    old_battery = set(previous.get("battery_names") or [])
    offline_names, battery_names = old_offline, old_battery           # unchanged while HA can't be read
    if not error:
        offline_names = {d["name"] for d in info.get("offline") or []}
        battery_names = {b["name"] for b in info.get("batteries") or []}
        for device in info.get("offline") or []:
            what = ", ".join(device["kinds"])
            found.append(issue("offline", device["name"], f"{device['name']} is offline in Home Assistant",
                               f"its {what} unavailable for {device['hours']} h", href="/#homeassistant"))
            if device["name"] not in old_offline:
                texts.append(Text(f"**🏠 {device['name']} dropped out of Home Assistant**\n• its {what} "
                                  f"{'has' if len(device['kinds']) == 1 else 'have'} been unavailable for "
                                  f"{device['hours']} h\n• check its power, batteries or Wi-Fi",
                                  f"ha:offline:{device['name']}"))
        for name in sorted(old_offline - offline_names):
            texts.append(Text(f"**✅ {name} is back in Home Assistant**", f"ha:offline:{name}"))
        for battery in info.get("batteries") or []:
            level = f"{battery['level']}%" if battery["level"] is not None else "low"
            found.append(issue("battery", battery["name"], f"{battery['name']}: battery {level}", "", "watch",
                               "/#homeassistant"))
            if battery["name"] not in old_battery:
                texts.append(Text(f"**🔋 {battery['name']}: battery {level}**\n• replace or charge it soon",
                                  f"ha:battery:{battery['name']}"))
        if info.get("updates"):
            found.append(issue("updates", "Home Assistant",
                               f"{len(info['updates'])} Home Assistant update{'s' if len(info['updates']) != 1 else ''} waiting",
                               ", ".join(u["title"] for u in info["updates"][:4]), "watch", "/#homeassistant"))
    report("homeassistant", found, now, store)

    for text in texts:
        if allowed(store, text, now):
            if send:
                send(text)
            elif notify.configured(settings.notify):
                notify.send(settings.notify, text)

    detail = {"checked_at": now.isoformat(timespec="seconds"), "error": error, "failures": failures, "info": info,
              "offline_names": sorted(offline_names), "battery_names": sorted(battery_names)}
    store.set_status("homeassistant", not [f for f in found if f.get("level", "problem") == "problem"], detail, now)
    return detail
