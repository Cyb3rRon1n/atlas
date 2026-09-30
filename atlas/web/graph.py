"""
Cytoscape elements for the interactive map (atlas web /map): one node per
inventory device, Proxmox guests nested inside their host, this host's
Docker networks nested inside the atlas host, all hanging off Internet ->
LAN. Pure: devices + topology in, plain dicts out.
"""


def _classes(*names):

    return " ".join(name for name in names if name)


def build_graph(devices, topology, include_ignored=False):

    topology = topology or {}
    # Both proxmox_host and brain are matched below by exact IP - if
    # proxmox.host (or the AI brain's configured address) is a hostname
    # rather than a literal IP, that match silently fails and guests
    # won't nest under their host.
    proxmox_host_ip = (topology.get("proxmox") or {}).get("host")
    brain = topology.get("brain") or {}
    networks = (topology.get("docker") or {}).get("networks") or {}

    shown = [device for device in devices if include_ignored or device["state"] != "ignored"]

    def has(device, source, test=lambda sighting: True):
        return any(sighting["source"] == source and test(sighting) for sighting in device["sightings"])

    proxmox_host = next((device for device in shown if proxmox_host_ip and any(
        sighting["source"] != "proxmox" and sighting.get("ip") == proxmox_host_ip for sighting in device["sightings"])), None)
    atlas_host = next((device for device in shown
                       if has(device, "lan", lambda sighting: (sighting.get("detail") or {}).get("self"))), None)

    parents = {}

    for device in shown:
        if proxmox_host and device is not proxmox_host and has(device, "proxmox"):
            parents[device["id"]] = f"d{proxmox_host['id']}"

    has_children = set(parents.values())

    if atlas_host and networks:
        has_children.add(f"d{atlas_host['id']}")

    nodes = [{"data": {"id": "internet", "label": "Internet"}, "classes": "fixed"},
             {"data": {"id": "lan", "label": "LAN"}, "classes": "fixed"}]
    edges = [{"data": {"id": "e:internet-lan", "source": "internet", "target": "lan"}}]

    for device in shown:

        node_id = f"d{device['id']}"
        label = device["name"]

        if brain.get("address") and device.get("ip") == brain["address"]:
            label += f"\nAI: {brain.get('model', '')}"

        data = {"id": node_id, "label": label, "device_id": device["id"], "status": device["status"],
                "state": device["state"], "kind": device["kind"], "ip": device.get("ip"),
                "important": device["important"]}

        if device["id"] in parents:
            data["parent"] = parents[device["id"]]
        else:
            edges.append({"data": {"id": f"e:lan-{node_id}", "source": "lan", "target": node_id}})

        nodes.append({"data": data, "classes": _classes(
            "device", f"status-{device['status']}", f"state-{device['state']}",
            "important" if device["important"] else "", "host" if node_id in has_children else "",
            "alert" if device["important"] and device["status"] == "quiet" else "")})

    if atlas_host:

        for name, members in networks.items():

            healthy = all(member["status"] == "running" and member.get("health") != "unhealthy" for member in members)
            nodes.append({"data": {"id": f"net:{name}", "label": f"{name} ({len(members)})",
                                   "parent": f"d{atlas_host['id']}"},
                          "classes": _classes("network", "status-seen" if healthy else "status-quiet")})

    return {"nodes": nodes, "edges": edges}
