import socket
from unittest.mock import MagicMock

from atlas.config.models import AtlasConfig, MapHost
from atlas.discovery.topology import collect_topology
from atlas.web.network_page import classify, render_network_page


def _container(name, networks=None, mode="bridge", labels=None, status="running", health=None, cid=None, ports=None):

    container = MagicMock()
    container.id = cid or name
    container.name = name
    container.status = status
    state = {"Status": status}
    if health:
        state["Health"] = {"Status": health}
    container.attrs = {
        "Config": {"Labels": labels or {}},
        "State": state,
        "HostConfig": {"NetworkMode": mode},
        "NetworkSettings": {"Networks": {n: {} for n in (networks or [])}, "Ports": ports or {}},
    }
    return container


def _docker():

    client = MagicMock()
    client.containers.list.return_value = [
        _container("jellyfin", ["stack_default"], labels={
            "traefik.http.routers.jf.rule": "Host(`jellyfin.example.com`)"}),
        _container("gluetun", ["stack_default"], cid="abc123", ports={
            "8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}], "8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8000"}]}),
        _container("crowdsec", ["stack_default"]),
        _container("qbittorrent", mode="container:abc123", health="unhealthy"),
    ]
    return client


def test_topology_groups_by_network_and_vpn_sharing_and_checks_lan():

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]

    config = AtlasConfig()
    config.name = "cyberpac"
    config.map.hosts = [MapHost(name="laptop", address="127.0.0.1", role="GPU", ports=[port])]
    config.proxmox.enabled = True

    try:
        topo = collect_topology(config, docker_client=_docker(),
                                proxmox_resources=[{"vmid": 200, "name": "mediabox", "type": "lxc", "status": "running", "cpu": 1}])
    finally:
        listener.close()

    networks = topo["docker"]["networks"]
    assert [c["name"] for c in networks["stack_default"]] == ["crowdsec", "gluetun", "jellyfin"]
    assert networks["via gluetun"][0]["health"] == "unhealthy"
    assert networks["stack_default"][2]["public"] == ["jellyfin.example.com"]
    assert networks["stack_default"][1]["ports"] == [8080]   # 127.0.0.1-only binds are not LAN-reachable
    assert topo["proxmox"]["guests"] == [{"vmid": 200, "name": "mediabox", "type": "lxc", "status": "running", "template": None}]
    assert topo["lan"][0]["reachable"] is True and topo["lan"][0]["open_ports"] == [port]
    assert topo["responsibility"]["proxmox_guests"]


def test_topology_without_docker_or_proxmox():

    topo = collect_topology(AtlasConfig())

    assert topo["docker"] == {"available": False, "networks": {}}
    assert topo["responsibility"]["proxmox_guests"] == ""


def test_latest_topology_skips_rows_other_commands_saved(temp_db):

    from atlas.intelligence.context import AtlasEnvironmentContext
    from atlas.knowledge.queries import KnowledgeQueries
    from atlas.knowledge.store import KnowledgeStore

    with_map = AtlasEnvironmentContext()
    with_map.update("topology", {"host": "cyberpac"})
    KnowledgeStore().save_environment(with_map)

    later = AtlasEnvironmentContext()
    later.update("virtualization", {"guests": []})
    KnowledgeStore().save_environment(later)

    assert KnowledgeQueries().latest_topology() == {"host": "cyberpac"}


ROUTES = [{"name": "jf", "hosts": ["jellyfin.example.com"], "entrypoints": ["websecure", "tunnel"], "protection": "public"},
          {"name": "lan", "hosts": ["lan.example.com"], "entrypoints": ["websecure"], "protection": "authelia"}]


def test_classify_internet_home_background_and_vpn():

    topo = collect_topology(AtlasConfig(), docker_client=_docker())
    lanes = classify(topo, ROUTES)

    assert [i["name"] for i in lanes["internet"]] == ["jellyfin"] and lanes["internet"][0]["protection"] == "own"
    assert [i["name"] for i in lanes["home"]] == ["gluetun"]        # published port, no route
    assert {i["name"] for i in lanes["background"]} == {"crowdsec", "qbittorrent"}
    qbit = next(i for i in lanes["background"] if i["name"] == "qbittorrent")
    assert qbit["vpn"] and qbit["state"] == "warn"                  # unhealthy sorts first in its lane
    assert lanes["background"][0]["name"] == "qbittorrent"


def test_network_page_lanes_tree_chips_and_escaping():

    topo = collect_topology(AtlasConfig(), docker_client=_docker())
    topo["docker"]["networks"]["stack_default"][0]["name"] = "<script>x</script>"
    graph = {"nodes": [{"data": {"id": "internet", "label": "Internet"}},
                       {"data": {"id": "d1", "label": "router", "device_id": 1, "status": "seen", "kind": "router"}},
                       {"data": {"id": "d2", "label": "nas", "device_id": 2, "status": "quiet", "kind": "server"}},
                       {"data": {"id": "g1", "label": "vm", "parent": "d2", "status": "seen"}},
                       {"data": {"id": "d3", "label": "192.168.1.50", "device_id": 3, "status": "seen"}}],
             "edges": [{"data": {"source": "internet", "target": "d1"}}, {"data": {"source": "d1", "target": "d2"}},
                       {"data": {"source": "d1", "target": "d3"}}],
             "hidden_wireless": 3}

    page = render_network_page(topo, ROUTES, graph)

    for text in ("From the internet", "Home network only", "Background (2)", "Machines", "Devices by connection",
                 'href="/devices/2"', "3 wireless devices hidden", "own login", "via VPN", 'data-ask="What is reachable'):
        assert text in page, text
    assert page.index('href="/devices/1"') < page.index('href="/devices/2"') < page.index(">vm<")
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page
    assert "1 unnamed devices" in page and page.index("1 unnamed devices") < page.index('href="/devices/3"')
    assert "cytoscape" not in page
    assert "atlas map" in render_network_page(None, [], None)
