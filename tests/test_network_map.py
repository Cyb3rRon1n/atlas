import socket
from unittest.mock import MagicMock

from atlas.config.models import AtlasConfig, MapHost
from atlas.discovery.topology import collect_topology
from atlas.web.render import MAP_SCRIPT, MAP_STYLE, render_map_page


def _container(name, networks=None, mode="bridge", labels=None, status="running", health=None, cid=None):

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
        "NetworkSettings": {"Networks": {n: {} for n in (networks or [])}},
    }
    return container


def _docker():

    client = MagicMock()
    client.containers.list.return_value = [
        _container("jellyfin", ["stack_default"], labels={
            "traefik.http.routers.jf.rule": "Host(`jellyfin.example.com`)"}),
        _container("gluetun", ["stack_default"], cid="abc123"),
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
    assert [c["name"] for c in networks["stack_default"]] == ["gluetun", "jellyfin"]
    assert networks["via gluetun"][0]["health"] == "unhealthy"
    assert networks["stack_default"][1]["public"] == ["jellyfin.example.com"]
    assert topo["proxmox"]["guests"] == [{"vmid": 200, "name": "mediabox", "type": "lxc", "status": "running", "template": None}]
    assert topo["lan"][0]["reachable"] is True and topo["lan"][0]["open_ports"] == [port]
    assert topo["responsibility"]["proxmox_guests"]


def test_topology_without_docker_or_proxmox():

    topo = collect_topology(AtlasConfig())

    assert topo["docker"] == {"available": False, "networks": {}}
    assert topo["responsibility"]["proxmox_guests"] == ""


def test_map_page_renders_svg_and_escapes_names():

    config = AtlasConfig()
    topo = collect_topology(config, docker_client=_docker())
    topo["docker"]["networks"]["stack_default"][0]["name"] = "<script>x</script>"

    page = render_map_page(topo)

    assert "<svg" in page and "Internet" in page and "What atlas is responsible for" in page
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page


def test_map_page_without_data_says_how_to_create_it():

    assert "atlas map" in render_map_page(None)


def test_map_page_has_interactive_graph_panel_and_vendored_scripts():

    config = AtlasConfig()
    page = render_map_page(collect_topology(config, docker_client=_docker()))

    assert '<div id="graph"' in page and '<aside id="panel" hidden' in page
    assert '<script src="/static/cytoscape.min.js?v=3.34.3"></script>' in page
    assert "cytoscape-dagre" not in page
    assert "<noscript>" in page and page.index("<noscript>") < page.index("<svg")
    assert 'id="show-ignored"' in page and "/api/graph" in page
    assert "innerHTML" not in page
    assert '<p id="graph-msg" class="muted"></p>' in page
    assert page.index('id="graph-msg"') < page.index('id="graph"')


def test_map_script_load_and_open_panel_handle_errors():

    assert "!response.ok || response.redirected" in MAP_SCRIPT
    assert MAP_SCRIPT.count("!response.ok || response.redirected") == 2
    assert "Couldn't load the map (status " in MAP_SCRIPT
    assert "network error" in MAP_SCRIPT
    assert "graphMsg.textContent" in MAP_SCRIPT


def test_map_script_save_sends_only_changed_fields_and_avoids_the_id_race():

    assert "const id = current.id;" in MAP_SCRIPT
    assert 'fetch("/api/devices/" + id,' in MAP_SCRIPT
    assert "openPanel(id, true);" in MAP_SCRIPT
    assert '"/api/devices/" + current.id' not in MAP_SCRIPT
    assert "Nothing changed." in MAP_SCRIPT
    assert 'current[key].join(",")' in MAP_SCRIPT


def test_map_script_layout_is_deterministic_preset_not_dagre():

    assert "cytoscape.use(cytoscapeDagre)" not in MAP_SCRIPT
    assert 'layout: {name: "preset"}' in MAP_SCRIPT
    assert "arrange(cy)" in MAP_SCRIPT
    assert "function arrange(cy) {" in MAP_SCRIPT
    assert "wheelSensitivity" not in MAP_SCRIPT
    assert '"opacity": 0.12' in MAP_SCRIPT


def test_map_script_keeps_saved_message_and_resizes_the_canvas():

    assert "async function openPanel(deviceId, keepMessage)" in MAP_SCRIPT
    assert "if (!keepMessage) message.textContent" in MAP_SCRIPT
    assert MAP_SCRIPT.count("cy.resize();") == 2
    assert MAP_SCRIPT.count("cy.fit(undefined, 20);") >= 2


def test_map_style_lets_the_panel_stay_on_screen():

    assert "min-width: 0" in MAP_STYLE
    assert "#panel { flex: 0 0 320px;" in MAP_STYLE
    assert "#panel input[type=checkbox] { width: auto; }" in MAP_STYLE


def test_map_page_without_topology_still_offers_the_graph():

    page = render_map_page(None)

    assert "atlas map" in page and '<div id="graph"' in page


def test_map_panel_links_to_chat():

    page = render_map_page(None)

    assert 'id="panel-ask"' in page and '"/chat?device=" + current.id' in page


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


def test_map_merges_same_machine_and_greys_templates():

    from atlas.web.render import render_map_svg

    topo = {
        "host": "cyberpac", "docker": {"available": True, "networks": {}},
        "proxmox": {"enabled": True, "host": "10.0.0.2", "guests": [
            {"vmid": 1000, "name": "tmpl", "type": "lxc", "status": "stopped", "template": True},
            {"vmid": 200, "name": "box", "type": "lxc", "status": "stopped", "template": False}]},
        "lan": [{"name": "cyberbox", "address": "10.0.0.2", "role": "", "reachable": True, "open_ports": [22]},
                {"name": "gpu", "address": "10.0.0.3", "role": "", "reachable": True, "open_ports": [11434]}],
        "brain": {"provider": "ollama", "model": "qwen3:8b", "address": "10.0.0.3", "reachable": True},
    }

    svg = render_map_svg(topo)

    assert ">Proxmox<" not in svg and ">AI brain<" not in svg
    assert "AI: qwen3:8b" in svg and "0/1 guests up" in svg
    assert 'stroke="#8b949e"' in svg   # template grey
    assert 'stroke="#f85149"' in svg   # stopped non-template red
