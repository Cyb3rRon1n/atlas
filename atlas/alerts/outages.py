"""
One alert per outage, not per device: when a switch, access point or the gateway is offline, the offline
devices cabled behind it (per the cabling map) fold under it. Only the topmost offline box counts, so a
dead core switch doesn't also report the dead edge switch behind it.
"""

BOXES = ("gateway", "switch", "ap")


def snapshots():
    """The last few cabling-map snapshots, newest first; [] without a map. A switch that just died often
    drops out of the newest scan, so older ones still say what was behind it."""

    try:
        from atlas.wiring.store import WiringStore
        return [row["snapshot"] for row in WiringStore().latest(3)]
    except Exception:
        return []


def outages(snaps, devices):
    """{down box device_id: [offline device ids behind it]} - only boxes with something offline behind them."""

    offline = {device["id"] for device in devices if device["status"] == "quiet" and device["state"] != "ignored"}
    names = [device["name"] for device in devices if device.get("name")]
    # "behind" lists names: one shared by two devices (two "iPhone"s) can't say which, so it is skipped
    by_name = {device["name"]: device["id"] for device in devices
               if device.get("name") and names.count(device["name"]) == 1}
    by_mac = {sighting["mac"].lower(): device["id"] for device in devices
              for sighting in device.get("sightings", []) if sighting.get("mac")}
    by_ip = {device["ip"]: device["id"] for device in devices if device.get("ip")}
    nodes, parent = {}, {}
    for snap in reversed(snaps or []):                      # oldest first, newer scans win
        for node in snap.get("nodes", []):           # switches/APs come from SNMP/UniFi: match them by MAC, then IP
            node = dict(node, device_id=node.get("device_id") or by_mac.get((node.get("mac") or "").lower())
                        or by_ip.get(node.get("ip")))
            nodes[node["id"]] = node
        parent.update({link["b"]: link["a"] for link in snap.get("links", [])})
    children = {}
    for child, up in parent.items():
        children.setdefault(up, []).append(child)

    def down(node_id):
        node = nodes.get(node_id) or {}
        return node.get("kind") in BOXES and node.get("device_id") in offline

    def ancestors(node_id):
        seen = set()
        while node_id in parent and node_id not in seen:
            seen.add(node_id)
            node_id = parent[node_id]
            yield node_id

    found = {}
    for node_id in nodes:
        if not down(node_id) or any(down(up) for up in ancestors(node_id)):
            continue
        behind, stack, seen = [], list(children.get(node_id, [])), set()
        while stack:
            child = stack.pop()
            if child in seen:
                continue
            seen.add(child)
            node = nodes.get(child) or {}
            ids = [node.get("device_id")] + [by_name.get(name) for name in node.get("behind", [])]
            behind += [device_id for device_id in ids if device_id in offline and device_id not in behind]
            stack += children.get(child, [])
        box = nodes[node_id]["device_id"]
        if behind := [device_id for device_id in behind if device_id != box]:
            found[box] = behind

    return found
