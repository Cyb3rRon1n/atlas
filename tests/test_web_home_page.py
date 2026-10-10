from types import SimpleNamespace

from atlas.web.home_page import build_hosts, interesting_events, render_home_page


TOPOLOGY = {
    "host": "cyberpac",
    "docker": {"networks": {"media": [
        {"name": "jellyfin", "status": "running", "health": "healthy"},
        {"name": "sonarr", "status": "running", "health": "unhealthy"},
        {"name": "old", "status": "exited", "health": ""},
    ]}},
    "proxmox": {"host": "192.168.10.97", "guests": [
        {"name": "mediabox", "status": "running", "template": False},
        {"name": "vm", "status": "stopped", "template": False},
        {"name": "tpl", "status": "stopped", "template": True},
    ]},
    "lan": [{"name": "cyberbox", "address": "192.168.10.97", "reachable": True}, {"name": "printer", "reachable": False}],
}
LOCAL = {"load_average": [3.0, 2.0, 1.0], "cpu_count": 12, "memory_percent": 40.0, "root_disk_percent": 43.0}
PVE = {"nodes": [{"name": "proxmox", "status": "online", "cpu": 0.051, "mem": 4, "maxmem": 16,
                  "disk": 30, "maxdisk": 100}]}
POSTURE_OK = {"state": "ok", "message": "All good", "vpn": "up", "routes": 12, "blocked": "3",
              "review_count": 0, "link": "/posture"}
EVENTS = [(SimpleNamespace(created_at="2026-10-10 12:00", event_type="atlas.proxmox.changes_detected",
                           source="<b>x</b>"), 3)]


def test_build_hosts_local_and_proxmox_rows():
    hosts = build_hosts(TOPOLOGY, LOCAL, PVE)
    local, node = hosts["rows"]
    assert local["name"] == "cyberpac" and local["cpu"] == 25 and local["mem"] == 40 and local["disk"] == 43
    assert local["detail"] == "2/3 containers running" and local["problems"] == ["sonarr unhealthy", "old stopped"]
    assert node["name"] == "cyberbox" and node["cpu"] == 5 and node["mem"] == 25 and node["disk"] == 30
    assert node["detail"] == "1/2 guests running" and node["problems"] == ["vm stopped"]
    assert hosts["down"] == ["printer"] and hosts["state"] == "warn"
    quiet = build_hosts({"lan": [{"name": "tv", "reachable": False}]}, LOCAL, None)
    assert quiet["down"] == ["tv"] and quiet["state"] == "ok"


def test_interesting_events_skips_routine_bookkeeping():
    events = [SimpleNamespace(event_type=t) for t in
              ("atlas.plugin.loaded", "atlas.proxmox.changes_detected", "atlas.discovery.completed", "device.new")]
    events.append(SimpleNamespace(event_type="atlas.proxmox.changes_detected"))
    assert [(e.event_type, n) for e, n in interesting_events(events, 1)] == [("atlas.proxmox.changes_detected", 2)]
    assert len(interesting_events(events)) == 2


def test_build_hosts_tolerates_missing_sources():
    hosts = build_hosts(None, None, None)
    assert hosts["rows"] == [] and hosts["state"] == "unknown"
    offline = build_hosts(None, None, {"nodes": [{"name": "pve", "status": "offline"}]})
    assert offline["rows"][0]["cpu"] is None and offline["state"] == "warn"


def test_home_all_good_verdict_cards_and_links():
    html = render_home_page(POSTURE_OK, build_hosts({"host": "cyberpac"}, LOCAL, None), EVENTS)
    assert ">All good<" in html
    for href in ('href="/posture"', 'href="/overview"', 'href="/history"'):
        assert href in html
    assert "Security posture" in html and "Hosts health" in html and "Recent activity" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html
    assert "proxmox changes detected" in html and "&times;3" in html
    assert 'aria-current="page" href="/"' in html or 'href="/" aria-current="page"' in html


def test_home_counts_attention_and_handles_unavailable():
    html = render_home_page({**POSTURE_OK, "state": "warn", "message": "VPN: down"},
                            build_hosts(TOPOLOGY, LOCAL, PVE), [])
    assert "2 things need attention" in html and "VPN: down" in html and "printer" in html
    empty = render_home_page(None, build_hosts(None, None, None), [])
    assert "Posture data unavailable" in empty and "No host data yet" in empty and "No events yet" in empty
