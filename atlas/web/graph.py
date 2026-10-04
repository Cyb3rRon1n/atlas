"""
Cytoscape elements for the interactive map (atlas web /map): one node per
inventory device, Proxmox guests nested inside their host, this host's
Docker networks nested inside the atlas host, all hanging off Internet ->
(router or LAN).

The root is the device whose `lan` sighting carries `detail["gateway"] is
True` (the default-gateway device found by a real scan) - that device
becomes "router" and there's no separate `lan` hub node. If several
devices carry a gateway-flagged sighting (a stale flag left behind by a
replaced router), the one whose gateway sighting has the latest
`last_seen` wins. Older data (or a scan that never saw a gateway) falls
back to today's `internet -> lan` hub, with `lan` playing the router's
role for every top-level device. The router is never nested (e.g. inside
a Proxmox host it also happens to be a guest of) - nesting it would leave
no top-level node for the layout to root the tree at.

A device whose effective `connection` is "wireless" is left out entirely
(no node, no edge) unless `include_wireless` - counted in `hidden_wireless`
- except the router itself, a Proxmox/atlas host with children, and any
device referenced by another shown device's `uplink_id` (an AP kept
visible purely because something's hanging off it). A top-level device
(no `parent`) whose `uplink_id` points at another shown, top-level device
gets an edge from that device instead of from the router/lan hub; nested
guests never get uplink edges, and a stale/hidden/ignored/nested uplink
target just falls back to the router/lan edge like any other device.

Pure: devices + topology in, plain dicts out.
"""


def _classes(*names):

    return " ".join(name for name in names if name)


def build_graph(devices, topology, include_ignored=False, include_wireless=False):

    topology = topology or {}
    # Both proxmox_host and brain are matched below by exact IP - if
    # proxmox.host (or the AI brain's configured address) is a hostname
    # rather than a literal IP, that match silently fails and guests
    # won't nest under their host.
    proxmox_host_ip = (topology.get("proxmox") or {}).get("host")
    brain = topology.get("brain") or {}
    networks = (topology.get("docker") or {}).get("networks") or {}

    candidates = [device for device in devices if include_ignored or device["state"] != "ignored"]

    def has(device, source, test=lambda sighting: True):
        return any(sighting["source"] == source and test(sighting) for sighting in device["sightings"])

    proxmox_host = next((device for device in candidates if proxmox_host_ip and any(
        sighting["source"] != "proxmox" and sighting.get("ip") == proxmox_host_ip for sighting in device["sightings"])), None)
    atlas_host = next((device for device in candidates
                       if has(device, "lan", lambda sighting: (sighting.get("detail") or {}).get("self"))), None)

    def gateway_sighting(device):
        return next((sighting for sighting in device["sightings"]
                     if sighting["source"] == "lan" and (sighting.get("detail") or {}).get("gateway") is True), None)

    # Several devices can carry a gateway-flagged lan sighting at once (a stale flag left
    # behind by a replaced router) - the one with the most recently seen gateway sighting
    # wins, not just whichever candidate happens to be first.
    gateway_candidates = [(device, gateway_sighting(device)) for device in candidates]
    gateway_candidates = [pair for pair in gateway_candidates if pair[1] is not None]
    router = max(gateway_candidates, key=lambda pair: pair[1].get("last_seen") or "")[0] if gateway_candidates else None

    parents = {}

    for device in candidates:
        # The router is never nested (e.g. a Proxmox-guest router): nesting it would leave
        # arrange() with no top-level node to root the tree at.
        if proxmox_host and device is not proxmox_host and device is not router and has(device, "proxmox"):
            parents[device["id"]] = f"d{proxmox_host['id']}"

    has_children = set(parents.values())

    if atlas_host and networks:
        has_children.add(f"d{atlas_host['id']}")

    def is_wireless(device):
        return device["connection"] == "wireless"

    def exempt_from_hiding(device):
        return (not is_wireless(device) or include_wireless
                or device is router or f"d{device['id']}" in has_children)

    # Exceptions are resolved in one pass: a device only counts as "someone's
    # uplink" when the device pointing at it already qualifies on its own
    # (router / host-with-children / not wireless) - no chasing a chain of
    # otherwise-hidden devices pointing at each other.
    base_shown = [device for device in candidates if exempt_from_hiding(device)]
    uplink_targets = {device["uplink_id"] for device in base_shown if device["uplink_id"] is not None}

    shown = [device for device in candidates if exempt_from_hiding(device) or device["id"] in uplink_targets]
    shown_ids = {device["id"] for device in shown}

    hidden_wireless = len(candidates) - len(shown)

    hub_id = f"d{router['id']}" if router else "lan"

    nodes = [{"data": {"id": "internet", "label": "Internet"}, "classes": "fixed"}]
    edges = []

    if router:
        edges.append({"data": {"id": f"e:internet-{hub_id}", "source": "internet", "target": hub_id}})
    else:
        nodes.append({"data": {"id": "lan", "label": "LAN"}, "classes": "fixed"})
        edges.append({"data": {"id": "e:internet-lan", "source": "internet", "target": "lan"}})

    def is_uplink_target(uplink_id, device_id):
        return (uplink_id is not None and uplink_id != device_id
               and uplink_id in shown_ids and uplink_id not in parents)

    for device in shown:

        node_id = f"d{device['id']}"
        label = device["name"]

        if brain.get("address") and device.get("ip") == brain["address"]:
            label += f"\nAI: {brain.get('model', '')}"

        data = {"id": node_id, "label": label, "device_id": device["id"], "status": device["status"],
                "state": device["state"], "kind": device["kind"], "ip": device.get("ip"),
                "important": device["important"], "connection": device["connection"],
                "uplink_id": device["uplink_id"]}

        if device["id"] in parents:
            data["parent"] = parents[device["id"]]
        elif device is not router:
            # The router already has its internet->hub_id edge above; falling through to
            # the hub-edge branch here would add a d{router}->d{router} self-loop.
            uplink_id = device["uplink_id"]
            source_id = f"d{uplink_id}" if is_uplink_target(uplink_id, device["id"]) else hub_id
            edges.append({"data": {"id": f"e:{source_id}-{node_id}", "source": source_id, "target": node_id}})

        nodes.append({"data": data, "classes": _classes(
            "device", f"status-{device['status']}", f"state-{device['state']}",
            "important" if device["important"] else "", "host" if node_id in has_children else "",
            "alert" if device["important"] and device["status"] == "quiet" else "",
            "router" if device is router else "", "infra" if device["kind"] == "network" else "",
            "conn-unknown" if device["connection"] == "unknown" else "",
            "conn-wireless" if device["connection"] == "wireless" else "")})

    if atlas_host:

        for name, members in networks.items():

            healthy = all(member["status"] == "running" and member.get("health") != "unhealthy" for member in members)
            nodes.append({"data": {"id": f"net:{name}", "label": f"{name} ({len(members)})",
                                   "parent": f"d{atlas_host['id']}"},
                          "classes": _classes("network", "status-seen" if healthy else "status-quiet")})

    return {"nodes": nodes, "edges": edges, "hidden_wireless": hidden_wireless}
