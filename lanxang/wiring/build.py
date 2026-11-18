"""
Merges the sources into one wired snapshot: SNMP switches (LLDP neighbours +
learned MACs), the optional UniFi view (its own devices' ports/uplinks and
which port each wired client is learned on), the operator's cabling.yaml and
the device inventory (names). Pure: data in, one dict out - no I/O, no clock.

Every link is oriented with `a` the upstream end (nearer the gateway, found by
a breadth-first walk over the infrastructure links), so the page can draw
downlinks on the bottom of a box and the uplink on top.

Heuristics, each with a known ceiling:
- An uplink port is one with an LLDP neighbour that is a switch/gateway/AP, or
  more than 3 non-virtual MACs (a hypervisor's guests use virtual MACs, so a
  Proxmox host with a few guests stays a host, not a "switch").
- On an access port the primary device is the LLDP-announcing host, else the
  first named non-virtual MAC, else the first non-virtual MAC; everything else on that port is listed as `behind`.
- A UniFi port with more than 3 wired clients and no managed device behind it
  is an unmanaged bridge (a dumb switch or an ISP router in bridge mode).
"""

import re
from collections import deque

from lanxang.wiring import is_virtual_mac, normalize_mac


INFRA = ("wan", "gateway", "switch", "ap")

MANY = 3

UNNAMED = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")   # inventory names an unnamed device by its IP


def _slug(name):

    return re.sub(r"\s+", "-", name or "").strip().lower()


def _port_info(info):

    return {"up": info["up"], "speed": info["speed"], **{key: info[key] for key in ("stp", "lag") if info.get(key)}}


IDLE = ("blocking", "discarding", "listening", "learning", "broken")


def _redundant(members, port_info, nodes):
    """Several cables between the same two infrastructure boxes: (kind, text), kind one of
    lag (bundled - fine), standby (spanning tree keeps all but one idle - fine), loop (more than one
    carries traffic) or unknown (no spanning-tree data from either end). Marks each link lag/standby."""

    a, b = nodes[members[0]["a"]]["name"], nodes[members[0]["b"]]["name"]
    ends = [(port_info.get((link["a"], link["a_port"]), {}), port_info.get((link["b"], link["b_port"]), {}))
            for link in members]

    for side in (0, 1):
        bundles = {end[side].get("lag") for end in ends}
        if len(bundles) == 1 and None not in bundles:
            name = bundles.pop()
            for link in members:
                link["lag"] = name
            return "lag", f"{a} ⇄ {b}: {len(members)} cables bundled as {name} (LACP)"

    spare = []
    for link, (end_a, end_b) in zip(members, ends):
        idle_port = (link["a_port"] if end_a.get("stp") in IDLE else
                     link["b_port"] if end_b.get("stp") in IDLE else None)
        link["standby"] = not link["up"] or idle_port is not None
        if link["standby"]:
            spare.append(idle_port or link["b_port"] or link["a_port"])
    carrying = sum(not link["standby"] for link in members)
    known = ["stp" in end_a or "stp" in end_b for end_a, end_b in ends]
    ports = ", ".join(link["a_port"] for link in members)

    if carrying <= 1 and any(known):
        return "standby", (f"Backup cable: {a} ⇄ {b} has {len(members)} cables; {', '.join(spare)} is on standby "
                           f"(spanning tree keeps it idle, so there is no loop). Fine as a spare - or bundle them "
                           f"(LACP) to use both.")
    if all(known):
        return "loop", (f"Loop risk: {len(members)} cables between {a} and {b} ({ports}) all carry traffic - "
                        f"spanning tree is not blocking any. Unplug one, or bundle them (LACP).")

    return "unknown", (f"{len(members)} links between {a} and {b} ({ports}) - spanning tree blocks all but one; "
                       f"remove one or bundle them (LACP)")


def build_wiring(switches, unifi, devices, cabling):

    unifi = unifi or {"devices": [], "clients": []}
    nodes, pending, links, warnings, notes, loops = {}, [], [], [], [], []
    port_info = {}

    inventory = {}
    for device in devices:
        for sighting in device.get("sightings") or []:
            mac = normalize_mac(sighting.get("mac"))
            if mac:
                inventory.setdefault(mac, device)

    clients = {client["mac"]: client for client in unifi["clients"]}

    def name_for(mac):
        device = inventory.get(mac)
        if device and device.get("name"):
            return device["name"], device["id"], device.get("ip") or ""
        client = clients.get(mac)
        if client and client["name"]:
            return client["name"], None, client["ip"]
        return mac, None, (client or {}).get("ip", "")

    def add_node(node_id, name, kind, ip="", mac=None, device_id=None):
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "name": name, "kind": kind, "ip": ip or "", "mac": mac,
                              "device_id": device_id, "behind": [], "ports": {}}
        return nodes[node_id]

    def host_node(mac):
        name, device_id, ip = name_for(mac)
        return add_node(f"h:{mac}", name, "host" if name != mac else "unknown", ip, mac, device_id)

    def add_link(a, a_port, b, b_port, via):
        info = port_info.get((a, a_port)) or port_info.get((b, b_port)) or {}
        link = {"id": f"{a}|{a_port}|{b}|{b_port}", "a": a, "a_port": a_port, "b": b, "b_port": b_port,
                "speed": info.get("speed", 0), "up": info.get("up", True), "via": via,
                "patch": None, "label": "", "color": ""}
        links.append(link)
        return link

    # --- UniFi devices (wireless-uplinked ones are hidden: this is the wired map) ---
    unifi_by_id, by_mac, port_macs = {}, {}, {}
    gateway = None

    for device in unifi["devices"]:
        if (device["uplink"] or {}).get("type") == "wireless":
            continue
        node_id = f"u:{device['mac']}"
        add_node(node_id, device["name"], device["role"], device["ip"], device["mac"])
        unifi_by_id[node_id], by_mac[device["mac"]] = device, node_id
        for port, info in device["ports"].items():
            port_info[(node_id, port)] = _port_info(info)
        for mac, port in device["port_macs"].items():
            port_macs[mac] = (node_id, port)

    def unifi_port(node_id, index):
        for port, info in (unifi_by_id.get(node_id) or {}).get("ports", {}).items():
            if info["index"] == index:
                return port
        return f"Port {index}" if index is not None else ""

    for node_id, device in unifi_by_id.items():
        uplink = device["uplink"] or {}
        if uplink.get("type") != "wire":
            continue
        local = unifi_port(node_id, uplink.get("local_port"))
        if uplink.get("mac") in by_mac:
            upstream = by_mac[uplink["mac"]]
            pending.append((upstream, unifi_port(upstream, uplink.get("remote_port")), node_id, local, "unifi"))
        elif device["role"] == "gateway" and local:
            add_node("wan", "Internet / ISP", "wan")
            pending.append(("wan", "", node_id, local, "unifi"))

    gateway = next((node_id for node_id, device in unifi_by_id.items() if device["role"] == "gateway"), None)

    # --- SNMP switches ---
    snmp = {}
    for switch in switches:
        node_id = f"s:{switch['name']}"
        add_node(node_id, switch["name"], "switch", switch["host"], switch.get("chassis_mac"))["model"] = switch.get("model", "")
        snmp[node_id] = switch
        for port, info in switch["ports"].items():
            port_info[(node_id, port)] = _port_info(info)

    chassis = {switch["chassis_mac"]: f"s:{switch['name']}" for switch in switches if switch.get("chassis_mac")}
    switch_hosts = {switch["host"]: f"s:{switch['name']}" for switch in switches}
    switch_macs = set(chassis)
    by_slug = {_slug(device["name"]): node_id for node_id, device in unifi_by_id.items()}

    uplink_ports, lldp_host, seen_pairs, unread = set(), {}, set(), []

    for node_id, switch in snmp.items():
        for neighbor in switch["neighbors"]:
            target, remote_port = None, neighbor["remote_port_desc"] or neighbor["remote_port"]
            if neighbor["remote_port_mac"] in port_macs:
                target, remote_port = port_macs[neighbor["remote_port_mac"]]
            elif neighbor["chassis_mac"] in port_macs:
                target, remote_port = port_macs[neighbor["chassis_mac"]]
            elif neighbor["chassis_mac"] in by_mac:
                target = by_mac[neighbor["chassis_mac"]]
            elif chassis.get(neighbor["chassis_mac"], node_id) != node_id:
                target = chassis[neighbor["chassis_mac"]]
            elif neighbor["sys_name"] and _slug(neighbor["sys_name"]) in by_slug:
                target = by_slug[_slug(neighbor["sys_name"])]

            if target is None:
                if neighbor["chassis_mac"]:
                    lldp_host[(node_id, neighbor["port"])] = neighbor["chassis_mac"]
                    if neighbor.get("caps"):      # a switch/router/AP atlas can't read yet: Setup suggests it
                        name, device_id, ip = name_for(neighbor["chassis_mac"])
                        unread.append({"switch": node_id, "port": neighbor["port"], "mac": neighbor["chassis_mac"],
                                       "sys_name": neighbor["sys_name"], "caps": neighbor["caps"], "ip": ip,
                                       "device_id": device_id})
                continue

            uplink_ports.add((node_id, neighbor["port"]))
            pair = frozenset({(node_id, neighbor["port"]), (target, remote_port)})
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                pending.append((target, remote_port, node_id, neighbor["port"], "lldp"))

    # A switch the UniFi side lists as a wired client tells us which UniFi port it hangs off.
    linked_ports = {(x, xp) for x, xp, _, _, _ in pending} | {(y, yp) for _, _, y, yp, _ in pending}
    for client in unifi["clients"]:
        node_id = switch_hosts.get(client["ip"])
        if node_id:
            switch_macs.add(client["mac"])
            upstream = by_mac.get(client["switch_mac"])
            port = unifi_port(upstream, client["switch_port"]) if upstream else ""
            already = any({x, y} == {upstream, node_id} for x, _, y, _, _ in pending)
            if upstream and port and (upstream, port) not in linked_ports and not already:
                pending.append((upstream, port, node_id, "", "unifi"))

    # --- orient infrastructure links: a = nearer the root ---
    adjacent = {}
    for x, _, y, _, _ in pending:
        adjacent.setdefault(x, set()).add(y)
        adjacent.setdefault(y, set()).add(x)

    root = "wan" if "wan" in nodes else gateway or next(iter(snmp), None)
    distance = {root: 0} if root else {}
    queue = deque([root] if root else [])
    while queue:
        current = queue.popleft()
        for other in adjacent.get(current, ()):
            if other not in distance:
                distance[other] = distance[current] + 1
                queue.append(other)

    far = len(nodes) + 1
    for x, xp, y, yp, via in pending:
        if distance.get(y, far) < distance.get(x, far):
            x, xp, y, yp = y, yp, x, xp
        add_link(x, xp, y, yp, via)

    # --- hosts behind SNMP access ports ---
    placed = set()
    known_infra = switch_macs | set(by_mac) | set(port_macs)

    for node_id, switch in snmp.items():
        per_port = {}
        for entry in switch["fdb"]:
            per_port.setdefault(entry["port"], [])
            if entry["mac"] not in per_port[entry["port"]]:
                per_port[entry["port"]].append(entry["mac"])

        for port, macs in per_port.items():
            if (node_id, port) in uplink_ports or sum(not is_virtual_mac(m) for m in macs) > MANY:
                uplink_ports.add((node_id, port))
                continue
            macs = [mac for mac in macs if mac not in known_infra]
            if not macs:
                continue
            preferred = lldp_host.get((node_id, port))
            physical = [mac for mac in macs if not is_virtual_mac(mac)] or macs
            # A named device beats an unnamed one (a server's BMC/IPMI NIC often sits on the same port).
            named = [mac for mac in physical if not UNNAMED.match(name_for(mac)[0]) and name_for(mac)[0] != mac]
            primary = preferred if preferred in macs else (named or physical)[0]
            host = host_node(primary)
            host["behind"] = [name_for(mac)[0] for mac in macs if mac != primary]
            add_link(node_id, port, host["id"], "", "fdb")
            placed.update(macs)

    # --- UniFi wired clients SNMP didn't place ---
    infra_ids = {node_id for node_id, node in nodes.items() if node["kind"] in INFRA}
    leads_to_infra = {(link["a"], link["a_port"]) for link in links if link["b"] in infra_ids}
    groups = {}

    for client in unifi["clients"]:
        if client["mac"] in placed or client["mac"] in known_infra or client["ip"] in switch_hosts:
            continue
        upstream = by_mac.get(client["switch_mac"])
        if not upstream or client["switch_port"] is None:
            continue
        groups.setdefault((upstream, unifi_port(upstream, client["switch_port"])), []).append(client)

    for (upstream, port), members in groups.items():
        if (upstream, port) in leads_to_infra:
            continue
        if len(members) > MANY:
            bridge = add_node(f"b:{upstream}:{port}", f"{len(members)} devices (unmanaged)", "bridge")
            bridge["behind"] = [name_for(client["mac"])[0] for client in members]
            add_link(upstream, port, bridge["id"], "", "unifi")
        else:
            for client in members:
                add_link(upstream, port, host_node(client["mac"])["id"], "", "unifi")

    # --- operator labels and patch panels ---
    for link in links:
        label = cabling["ports"].get(f"{nodes[link['a']]['name']}:{link['a_port']}")
        if label:
            link["label"], link["color"] = label["label"], label["color"]
            if nodes[link["b"]]["kind"] == "bridge" and label["label"]:
                nodes[link["b"]]["name"] = label["label"]

    by_name = {node["name"]: node_id for node_id, node in nodes.items()}
    panels = []

    for entry in cabling["panels"]:
        tag = f"{entry['panel']}-{entry['port']:02d}"
        switch_id = by_name.get(entry["switch"])
        known_ports = {port for (owner, port) in port_info if owner == switch_id}
        if switch_id is None:
            warnings.append(f"{tag}: no switch named {entry['switch']}")
        elif entry["switch_port"] not in known_ports:
            warnings.append(f"{tag}: {entry['switch']} has no port {entry['switch_port']}")

        matches = [link for link in links if link["a"] == switch_id and link["a_port"] == entry["switch_port"]] \
            or [link for link in links if link["b"] == switch_id and link["b_port"] == entry["switch_port"]]
        for link in matches:
            link["patch"] = tag
            link["label"] = entry["label"] or link["label"]
            link["color"] = entry["color"] or link["color"]

        info = port_info.get((switch_id, entry["switch_port"]), {})
        other = (matches[0]["b"] if matches[0]["a"] == switch_id else matches[0]["a"]) if matches else None
        panels.append({**entry, "device": nodes[other]["name"] if other else "",
                       "speed": info.get("speed", 0), "up": info.get("up", False)})

    # --- warnings ---
    pairs = {}
    for link in links:
        pairs.setdefault(frozenset((link["a"], link["b"])), []).append(link)
    for pair, members in pairs.items():
        if len(members) > 1 and all(nodes[node_id]["kind"] in INFRA for node_id in pair):
            kind, text = _redundant(members, port_info, nodes)
            (warnings if kind in ("loop", "unknown") else notes).append(text)
            if kind == "loop":
                loops.append(" ⇄ ".join(sorted(nodes[node_id]["name"] for node_id in pair)))

    if cabling.get("error"):
        warnings.append(cabling["error"])

    # --- ports used, drop orphans ---
    for link in links:
        for side, port in ((link["a"], link["a_port"]), (link["b"], link["b_port"])):
            if port:
                nodes[side]["ports"][port] = port_info.get((side, port), {"up": link["up"], "speed": link["speed"]})

    used = {link["a"] for link in links} | {link["b"] for link in links} | ({gateway} if gateway else set())

    return {"nodes": [node for node_id, node in nodes.items() if node_id in used], "links": links,
            "panels": panels, "warnings": warnings, "notes": notes, "loops": loops, "unread": unread}
