from types import SimpleNamespace

from atlas.web.home_page import attention_items, build_hosts, build_storage, interesting_events, parse_mdstat, render_home_page


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
    assert "\u2713 All good" in html and "Needs attention" not in html
    for href in ('href="/posture"', 'href="/overview"', 'href="/history"'):
        assert href in html
    assert "Security posture" in html and "Hosts health" in html and "Recent activity" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html
    assert "proxmox changes detected" in html and "&times;3" in html
    assert 'aria-current="page" href="/"' in html or 'href="/" aria-current="page"' in html


def test_home_counts_attention_and_handles_unavailable():
    html = render_home_page({**POSTURE_OK, "state": "warn", "message": "VPN: down"},
                            build_hosts(TOPOLOGY, LOCAL, PVE), [])
    assert "Needs attention" in html and "VPN: down" in html and "printer" in html
    assert "cyberbox: vm stopped" in html and "cyberpac: sonarr unhealthy, old stopped" in html
    assert html.count("needs attention</span>") == 2   # posture + hosts cards flagged
    empty = render_home_page(None, build_hosts(None, None, None), [])
    assert "Posture data unavailable" in empty and "No host data yet" in empty and "No events yet" in empty


MDSTAT = """Personalities : [raid0] [raid1]
md0 : active raid0 sdh[5] sdd[1] sdb[3] sde[7] sdc[2] sdg[4] sda[0] sdf[6]
      26754215936 blocks super 1.2 512k chunks

md1 : active raid1 sdx[1](F) sdy[0]
      976630464 blocks super 1.2 [2/1] [U_]

unused devices: <none>
"""


def test_parse_mdstat_raid0_and_degraded_mirror():
    md0, md1 = parse_mdstat(MDSTAT)
    assert md0 == {"name": "md0", "state": "active", "level": "raid0", "disks": 8, "failed": 0, "degraded": False}
    assert md1["failed"] == 1 and md1["degraded"] is True
    assert parse_mdstat("") == [] and parse_mdstat(None) == []


def test_build_storage_rows_and_warnings():
    usage = {"media array": SimpleNamespace(percent=58.2, total=25e12)}
    feeds = {"raid_card_watchdog": {"temp": 42, "state": "ok"}, "other": {"error": "timeout"}}
    pve = {"nodes": [{"name": "proxmox", "zfs": [{"name": "bulk", "health": "ONLINE", "size": 100, "alloc": 70},
                                                 {"name": "fast", "health": "DEGRADED", "size": 100, "alloc": 10}]}]}
    storage = build_storage(parse_mdstat(MDSTAT)[:1], usage, feeds, pve, TOPOLOGY)
    rows = {r["name"]: r for r in storage["rows"]}
    assert rows["md0"]["detail"] == "RAID0 · 8 disks · active · no redundancy" and not rows["md0"]["warn"]
    assert rows["media array"]["detail"] == "58% of 25.0 TB" and not rows["media array"]["warn"]
    assert rows["raid card watchdog"]["detail"] == "42°C · ok" and rows["other"]["warn"]
    assert not rows["cyberbox bulk"]["warn"] and rows["cyberbox fast"]["warn"]
    assert storage["state"] == "warn"
    assert build_storage([], {}, None, None)["state"] == "unknown"


def test_home_new_cards_chips_and_chart():
    trends = {"hours": [{"hour": f"2026-10-10T{h:02d}:00:00", "direct": h * 10, "vpn": 5} for h in range(24)],
              "new_per_day": [{"day": f"2026-10-0{d}", "count": d} for d in range(1, 8)]}
    analysis = {"summary": "All <fine>", "model": "qwen3:8b", "created_at": "2026-10-10 06:00:00",
                "recommendations": [{"title": "Fan", "severity": "high"}, {"title": "a"}, {"title": "b"}, {"title": "c"}]}
    from datetime import datetime
    html = render_home_page(POSTURE_OK, build_hosts(None, LOCAL, None), [], storage={"rows": [], "state": "ok"},
                            trends=trends, analysis=analysis, now=datetime(2026, 10, 10, 12))
    assert 'data-ask="What changed today?"' in html and "window.atlasAsk" in html
    assert "Security trends" in html and html.count("<rect") > 24 and "28 total" in html
    assert "6 h ago" in html and "All &lt;fine&gt;" in html and ">Fan<" not in html and " Fan</li>" in html
    assert html.count("<li>") == 3   # top 3 recommendations only
    assert "No check-up yet" in render_home_page(None, build_hosts(None, None, None), [])


def test_attention_items_name_the_problem_and_link_to_the_fix():
    posture = {**POSTURE_OK, "state": "review", "review_count": 40}
    storage = {"rows": [{"name": "md0", "detail": "RAID1 · DEGRADED (1 failed)", "warn": True},
                        {"name": "media array", "detail": "58%", "warn": False}], "state": "warn"}
    items = attention_items(posture, build_hosts(None, LOCAL, None), storage)
    assert items == [("posture", "Security posture", "40 new outbound destinations need review", "/posture#review", "Review"),
                     ("storage", "Storage", "md0: RAID1 · DEGRADED (1 failed)", "/overview", "Details")]
    html = render_home_page(posture, build_hosts(None, LOCAL, None), [], storage=storage)
    assert 'href="/posture#review">Review' in html and "hcard review flagged" in html
