from lanxang.web.hosts_page import build_history, render_hosts_summary
from lanxang.web.render import render_overview_page


HOSTS = {"rows": [{"name": "homeserver", "cpu": 20, "mem": 50, "disk": 40, "detail": "", "problems": []}]}
STORAGE = {"rows": []}
TOPOLOGY = {"docker": {"networks": {"web": [{"name": "app", "status": "running"}]}},
            "proxmox": {"guests": [{"name": "vm1", "status": "running"}]},
            "lan": [{"name": "nas", "reachable": True}, {"name": "tv", "reachable": False}]}
HISTORY = {"homeserver": {"cpu": [10, 20, 30], "mem": [40, 41, 42], "disk": [50, 50, 51]}}


def test_overview_host_trend_lines():

    html = render_hosts_summary(HOSTS, STORAGE, TOPOLOGY, HISTORY)
    box = html.split('<section class="hbox')[1]
    assert box.count("<polyline") == 3
    assert "<title>homeserver CPU" in box

    assert "<polyline" not in render_hosts_summary(HOSTS, STORAGE, TOPOLOGY)
    assert "<polyline" not in render_hosts_summary(HOSTS, STORAGE, TOPOLOGY, {"other": HISTORY["homeserver"]})


def test_overview_short_list_and_raw_disclosure():

    html = render_hosts_summary(HOSTS, STORAGE, TOPOLOGY)
    assert '<a href="#containers">1 container</a>' in html
    assert '<a href="#guests">1 Proxmox guest</a>' in html
    assert '<a href="/devices">2 LAN hosts</a>' in html

    page = render_overview_page({"system": {"os": "Linux"}}, None, html)
    assert '<details class="raw"><summary>Raw snapshot</summary>' in page


def test_build_history_maps_host_and_proxmox_node():

    samples = [(None, {"cpu": 1, "mem": 2, "disk": 3}), (None, {"cpu": 4, "mem": None, "disk": 6})]
    scans = [(None, {"nodes": [{"name": "pve", "cpu": 0.25, "mem": 50, "maxmem": 100, "disk": 1, "maxdisk": 4}]}),
             (None, {"nodes": [{"name": "pve", "status": "offline"}]})]
    history = build_history(samples, scans, "homeserver", {"pve": "nas"})
    assert history["homeserver"] == {"cpu": [1, 4], "mem": [2, None], "disk": [3, 6]}
    assert history["nas"]["cpu"] == [25.0] and history["nas"]["mem"] == [50.0] and history["nas"]["disk"] == [25.0]
    assert build_history([], [], "x", {}) == {}
