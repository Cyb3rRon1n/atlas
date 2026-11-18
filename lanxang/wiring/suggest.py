"""
Devices that could show their ports if atlas had a login: they answer SNMPv3 discovery (lanxang ports check)
or a mapped switch hears them announce themselves as a bridge/router/AP over LLDP. Lanxang only suggests -
the Setup tab's Switches card asks for the SNMPv3 user and passphrases, tests them, then saves.
"""

NOT_SWITCHES = {"net-snmp (Linux)", "VMware", "Synology", "QNAP"}     # SNMP agents that aren't network gear


def suggestions(settings, ports_state, snapshot, devices):
    """[{"ip", "mac", "name", "device_id", "why": [...], "suggested_name"}], strongest signals first."""

    wiring = settings.wiring
    skip = {value.lower() for value in wiring.not_managed} | {switch.host for switch in wiring.switches}
    mapped = {node.get("ip") for node in (snapshot or {}).get("nodes", [])
              if node.get("kind") in ("switch", "gateway", "ap") and node.get("ip")}
    by_ip = {device["ip"]: device for device in devices if device.get("ip")}
    by_mac = {sighting["mac"].lower(): device for device in devices for sighting in device.get("sightings", [])
              if sighting.get("mac")}
    found = {}

    def add(ip, mac, why, sys_name=""):
        device = by_ip.get(ip) or by_mac.get((mac or "").lower())
        ip = ip or (device or {}).get("ip") or ""
        if not ip or ip in skip or ip in mapped or (mac or "").lower() in skip:
            return
        entry = found.setdefault(ip, {"ip": ip, "mac": mac or "", "name": (device or {}).get("name") or sys_name or ip,
                                      "device_id": (device or {}).get("id"), "why": [],
                                      "suggested_name": sys_name or (device or {}).get("name") or ""})
        if why not in entry["why"]:
            entry["why"].append(why)

    for ip, info in ((ports_state or {}).get("snmp") or {}).items():
        if info.get("vendor") not in NOT_SWITCHES:
            add(ip, "", f"answers SNMPv3 ({info['vendor'] or 'unknown maker'})")

    for neighbor in (snapshot or {}).get("unread", []):
        add(neighbor.get("ip"), neighbor.get("mac"),
            f"announces itself as a {' / '.join(neighbor['caps'])} on {neighbor['switch'].split(':', 1)[-1]} "
            f"port {neighbor['port']}", neighbor.get("sys_name") or "")

    return sorted(found.values(), key=lambda entry: (-len(entry["why"]), entry["name"].lower()))


def current(devices=None):
    """Suggestions from the latest saved data; [] when anything is missing - a page never fails over this."""

    try:
        from lanxang.config.loader import load_config
        from lanxang.devices.store import InventoryStore
        from lanxang.posture.store import PostureStore
        from lanxang.wiring.store import WiringStore

        rows = WiringStore().latest(1)
        ports = (PostureStore().statuses().get("ports") or {}).get("detail") or {}
        return suggestions(load_config(), ports, rows[0]["snapshot"] if rows else None,
                           InventoryStore().devices() if devices is None else devices)
    except Exception:
        return []
