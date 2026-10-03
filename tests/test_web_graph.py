from atlas.web.graph import build_graph


def device(id, name, sightings, state="known", status="seen", important=False, kind="other"):

    return {"id": id, "name": name, "kind": kind, "tags": [], "notes": "", "important": important,
            "state": state, "status": status, "ip": sightings[0].get("ip") if sightings else None,
            "last_seen": None, "sightings": sightings}


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

    edges = {(edge["data"]["source"], edge["data"]["target"]) for edge in build_graph(DEVICES, TOPOLOGY)["edges"]}

    assert ("internet", "lan") in edges
    assert {("lan", "d1"), ("lan", "d2"), ("lan", "d4"), ("lan", "d5")} <= edges
    assert ("lan", "d3") not in edges
    assert all(len(edge) == 2 for edge in edges)


def test_ignored_can_be_included_and_no_topology_still_works():

    assert "d6" in nodes(build_graph(DEVICES, TOPOLOGY, include_ignored=True))

    bare = nodes(build_graph(DEVICES, None))
    assert "d3" in bare and "parent" not in bare["d3"]["data"]
    assert not any(key.startswith("net:") for key in bare)
