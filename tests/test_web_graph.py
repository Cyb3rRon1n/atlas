from atlas.web.graph import build_graph


def device(id, name, sightings, state="known", status="seen", important=False, kind="other",
           connection="unknown", connection_guessed=False, uplink_id=None):

    return {"id": id, "name": name, "kind": kind, "tags": [], "notes": "", "important": important,
            "state": state, "status": status, "ip": sightings[0].get("ip") if sightings else None,
            "last_seen": None, "sightings": sightings,
            "connection": connection, "connection_guessed": connection_guessed, "uplink_id": uplink_id}


def lan(ip, **detail):

    return {"source": "lan", "ip": ip, "detail": detail}


TOPOLOGY = {
    "proxmox": {"host": "192.168.10.97"},
    "brain": {"address": "192.168.10.19", "model": "qwen3:8b"},
    "docker": {"networks": {
        "stack_default": [{"name": "jellyfin", "status": "running", "health": "healthy", "public": []},
                          {"name": "sonarr", "status": "running", "health": "", "public": []}],
        "guac": [{"name": "guacd", "status": "exited", "health": "", "public": []}],
    }},
}

DEVICES = [
    device(1, "cyberpac", [lan("192.168.10.157", self=True)]),
    device(2, "cyberbox", [lan("192.168.10.97"), {"source": "manual", "ip": "192.168.10.97", "detail": {}}]),
    device(3, "mediabox", [lan("192.168.10.57"), {"source": "proxmox", "ip": None, "detail": {"type": "lxc"}}]),
    device(4, "MSI laptop", [lan("192.168.10.19")], important=True, status="quiet"),
    device(5, "phone", [lan("192.168.10.88")], state="new"),
    device(6, "old tv", [lan("192.168.10.70")], state="ignored"),
]


def nodes(graph):

    return {node["data"]["id"]: node for node in graph["nodes"]}


def edge_pairs(graph):

    return {(edge["data"]["source"], edge["data"]["target"]) for edge in graph["edges"]}


def test_nesting_labels_and_classes():

    graph = build_graph(DEVICES, TOPOLOGY)
    by_id = nodes(graph)

    assert by_id["d3"]["data"]["parent"] == "d2"
    assert by_id["net:stack_default"]["data"]["parent"] == "d1"
    assert by_id["net:stack_default"]["data"]["label"] == "stack_default (2)"
    assert "status-seen" in by_id["net:stack_default"]["classes"]
    assert "status-quiet" in by_id["net:guac"]["classes"]
    assert by_id["d4"]["data"]["label"] == "MSI laptop\nAI: qwen3:8b"
    assert "alert" in by_id["d4"]["classes"] and "important" in by_id["d4"]["classes"]
    assert "state-new" in by_id["d5"]["classes"]
    assert "host" in by_id["d1"]["classes"] and "host" in by_id["d2"]["classes"]
    assert "d6" not in by_id


def test_edges_connect_internet_lan_and_top_level_devices_only():

    edges = edge_pairs(build_graph(DEVICES, TOPOLOGY))

    assert ("internet", "lan") in edges
    assert {("lan", "d1"), ("lan", "d2"), ("lan", "d4"), ("lan", "d5")} <= edges
    assert ("lan", "d3") not in edges
    assert all(len(edge) == 2 for edge in edges)


def test_ignored_can_be_included_and_no_topology_still_works():

    assert "d6" in nodes(build_graph(DEVICES, TOPOLOGY, include_ignored=True))

    bare = nodes(build_graph(DEVICES, None))
    assert "d3" in bare and "parent" not in bare["d3"]["data"]
    assert not any(key.startswith("net:") for key in bare)


def test_router_is_root_with_no_lan_node():

    devices = [device(1, "router", [lan("192.168.10.1", gateway=True)], kind="network"),
               device(2, "pc", [lan("192.168.10.2")])]

    graph = build_graph(devices, None)
    by_id = nodes(graph)
    edges = edge_pairs(graph)

    assert "lan" not in by_id
    assert "router" in by_id["d1"]["classes"]
    assert ("d1", "d1") not in edges
    assert edges == {("internet", "d1"), ("d1", "d2")}


def test_router_chosen_by_latest_gateway_sighting_when_several_flagged():

    devices = [device(1, "old-router", [lan("192.168.10.1", gateway=True) | {"last_seen": "2026-01-01T00:00:00"}],
                      kind="network"),
               device(2, "new-router", [lan("192.168.10.254", gateway=True) | {"last_seen": "2026-06-01T00:00:00"}],
                      kind="network"),
               device(3, "pc", [lan("192.168.10.2")])]

    graph = build_graph(devices, None)
    by_id = nodes(graph)

    assert "router" in by_id["d2"]["classes"]
    assert "router" not in by_id["d1"]["classes"]
    assert ("internet", "d2") in edge_pairs(graph)


def test_router_is_never_nested_even_if_it_is_a_proxmox_guest():

    topology = {"proxmox": {"host": "192.168.10.10"}}

    devices = [
        device(1, "proxmox-host", [lan("192.168.10.10")], kind="container-host"),
        device(2, "router-guest", [lan("192.168.10.1", gateway=True),
                                   {"source": "proxmox", "ip": None, "detail": {"type": "lxc"}}], kind="network"),
        device(3, "pc", [lan("192.168.10.2")]),
    ]

    graph = build_graph(devices, topology)
    by_id = nodes(graph)
    edges = edge_pairs(graph)

    assert "parent" not in by_id["d2"]["data"]
    assert ("internet", "d2") in edges
    assert ("d2", "d3") in edges


def test_fallback_lan_hub_used_when_no_gateway_flag():

    devices = [device(1, "ap", [lan("192.168.10.1")], kind="network"),
               device(2, "pc", [lan("192.168.10.2")])]

    graph = build_graph(devices, None)

    assert "lan" in nodes(graph)
    assert {("lan", "d1"), ("lan", "d2")} <= edge_pairs(graph)


def test_wireless_device_hidden_unless_included():

    devices = [device(1, "router", [lan("192.168.10.1", gateway=True)], kind="network"),
               device(2, "phone", [lan("192.168.10.2")], kind="phone",
                      connection="wireless", connection_guessed=True)]

    hidden = build_graph(devices, None)
    assert "d2" not in nodes(hidden)
    assert hidden["hidden_wireless"] == 1

    shown = build_graph(devices, None, include_wireless=True)
    by_id = nodes(shown)
    assert "d2" in by_id and "conn-wireless" in by_id["d2"]["classes"]
    assert shown["hidden_wireless"] == 0


def test_operator_set_wired_phone_is_shown():

    devices = [device(1, "router", [lan("192.168.10.1", gateway=True)], kind="network"),
               device(2, "phone", [lan("192.168.10.2")], kind="phone", connection="wired")]

    graph = build_graph(devices, None)

    assert "d2" in nodes(graph)
    assert graph["hidden_wireless"] == 0


def test_uplink_edge_replaces_router_edge():

    devices = [device(1, "router", [lan("192.168.10.1", gateway=True)], kind="network"),
               device(2, "ap", [lan("192.168.10.2")], kind="network"),
               device(3, "pc", [lan("192.168.10.3")], uplink_id=2)]

    edges = edge_pairs(build_graph(devices, None))

    assert ("d2", "d3") in edges
    assert ("d1", "d3") not in edges


def test_uplink_to_a_hidden_ignored_or_nested_device_falls_back_to_router():

    topology = {"proxmox": {"host": "192.168.10.10"}}

    devices = [
        device(1, "router", [lan("192.168.10.1", gateway=True)], kind="network"),
        # "hidden": uplink_id points at a device id that doesn't exist at all.
        device(2, "pc-to-nowhere", [lan("192.168.10.2")], uplink_id=999),
        # "ignored": the target exists but is filtered out (not included).
        device(3, "ignored-ap", [lan("192.168.10.3")], state="ignored", kind="network"),
        device(4, "pc-to-ignored", [lan("192.168.10.4")], uplink_id=3),
        # "nested": the target exists and is shown, but nested under the proxmox host.
        device(5, "proxmox-host", [lan("192.168.10.10")], kind="container-host"),
        device(6, "guest", [{"source": "proxmox", "ip": None, "detail": {"type": "lxc"}}], kind="lxc"),
        device(7, "pc-to-nested", [lan("192.168.10.5")], uplink_id=6),
    ]

    edges = edge_pairs(build_graph(devices, topology))

    assert ("d1", "d2") in edges
    assert ("d1", "d4") in edges
    assert ("d1", "d7") in edges


def test_wireless_ap_that_is_someones_uplink_stays_shown():

    devices = [device(1, "router", [lan("192.168.10.1", gateway=True)], kind="network"),
               device(2, "wireless-ap", [lan("192.168.10.2")], kind="network",
                      connection="wireless", connection_guessed=True),
               device(3, "pc", [lan("192.168.10.3")], uplink_id=2)]

    graph = build_graph(devices, None)
    by_id = nodes(graph)

    assert "d2" in by_id
    assert graph["hidden_wireless"] == 0
    assert ("d2", "d3") in edge_pairs(graph)
