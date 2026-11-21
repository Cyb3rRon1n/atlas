import re
from types import SimpleNamespace

from lanxang.web.home_page import attention_items, build_hosts, build_storage, interesting_events, parse_mdstat, render_home_page


TOPOLOGY = {
    "host": "media-server",
    "docker": {"networks": {"media": [
        {"name": "jellyfin", "status": "running", "health": "healthy"},
        {"name": "sonarr", "status": "running", "health": "unhealthy"},
        {"name": "old", "status": "exited", "health": ""},
    ]}},
    "proxmox": {"host": "192.168.50.97", "guests": [
        {"name": "fileserver", "status": "running", "template": False},
        {"name": "vm", "status": "stopped", "template": False},
        {"name": "tpl", "status": "stopped", "template": True},
    ]},
    "lan": [{"name": "pve-host", "address": "192.168.50.97", "reachable": True}, {"name": "printer", "reachable": False}],
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
    assert local["name"] == "media-server" and local["cpu"] == 25 and local["mem"] == 40 and local["disk"] == 43
    assert local["detail"] == "2/3 containers running" and local["problems"] == ["sonarr unhealthy", "old stopped"]
    assert node["name"] == "pve-host" and node["cpu"] == 5 and node["mem"] == 25 and node["disk"] == 30
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
    from datetime import datetime
    now = datetime(2026, 10, 10, 12)
    html = render_home_page(POSTURE_OK, build_hosts({"host": "media-server"}, LOCAL, None), EVENTS, now=now,
                            last_scan=now)
    assert "Everything is healthy" in html and 'class="hero ok"' in html and "Needs attention" not in html
    for href in ('href="/posture"', 'href="/overview"', 'href="/history"'):
        assert href in html
    assert "Security posture" in html and "Host health" in html and "Recent activity" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html
    assert "proxmox changes detected" in html and "&times;3" in html
    assert 'href="/?home" aria-current="page"' in html


def test_home_counts_attention_and_handles_unavailable():
    html = render_home_page({**POSTURE_OK, "state": "warn", "message": "VPN: down"},
                            build_hosts(TOPOLOGY, LOCAL, PVE), [])
    assert "Needs attention" in html and "VPN: down" in html and "printer" in html
    assert "pve-host: vm stopped" in html and "media-server: sonarr unhealthy, old stopped" in html
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
    assert not rows["pve-host bulk"]["warn"] and rows["pve-host fast"]["warn"]
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
    assert "today 06:00 UTC</time>" in html and "All &lt;fine&gt;" in html and ">Fan<" not in html and " Fan</li>" in html
    assert html.split("<main")[1].count("<li>") == 3   # top 3 recommendations only
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


def test_hosts_summary_meters_storage_and_container_chips():
    from lanxang.web.hosts_page import render_hosts_summary
    html = render_hosts_summary(build_hosts(TOPOLOGY, LOCAL, PVE), {"rows": [{"name": "md0", "detail": "ok", "warn": False}]}, TOPOLOGY)
    assert "media-server" in html and "pve-host" in html and 'style="width:25%"' in html
    assert "Storage &amp; RAID" in html and "media (3)" in html and "Proxmox guests (2)" in html
    assert 'class="dot down"' in html and 'data-ask="What is using the most CPU' in html


def test_home_attention_lists_new_sign_in_places():
    html = render_home_page(POSTURE_OK, build_hosts(None, LOCAL, None), [],
                            access_reviews=[{"user": "dave", "label": "Lisbon, PT \u00b7 MEO"}])
    assert "dave signed in from a new place: Lisbon, PT" in html and 'href="/access">Review' in html


def test_getting_started_checklist_until_the_required_steps_are_done():
    from lanxang.config.models import AtlasConfig
    from lanxang.web.home_page import setup_steps

    hosts = {"rows": [], "down": [], "state": "unknown"}
    fresh = setup_steps(AtlasConfig(), [{"state": "new"}, {"state": "new"}, {"state": "known"}])
    page = render_home_page(None, hosts, [], steps=fresh)
    assert "Getting started" in page and "2 devices still marked new" in page
    assert 'href="/settings#ntfy"' in page and "(optional)" in page

    config = AtlasConfig(notify={"ntfy": {"url": "https://ntfy.example.org", "topic": "t"}})
    done = setup_steps(config, [{"state": "known"}])
    assert [step[3] for step in done] == [True, True, False, False]
    assert "Getting started" not in render_home_page(None, hosts, [], steps=done)   # optional steps don't keep it up
    assert "Getting started" not in render_home_page(None, hosts, [])


def test_home_headline_tiles_and_problem_rows():
    from datetime import datetime
    from lanxang.web.home_page import build_vitals

    hosts = build_hosts(None, LOCAL, None)
    ups = {"upses": {"rack": {"state": "battery", "charge": 80.0}}}
    vitals = build_vitals([], None, None, ["ok"] * 7, None, POSTURE_OK, ups)
    now = datetime(2026, 10, 10, 12)
    html = render_home_page({**POSTURE_OK, "state": "warn", "message": "VPN: down"}, hosts, EVENTS, vitals=vitals,
                            now=now, last_scan=now)
    assert '<p class="hero-title">1 thing needs a look — everything else is healthy</p>' in html
    assert 'class="vitals"' in html and "On battery" in html and 'class="checkrow todo"' in html and "VPN: down" in html


def test_a_degraded_pool_is_one_line_that_links_to_its_alert():
    from lanxang.web.home_page import attention_items

    storage = {"rows": [{"name": "nas tank", "detail": "DEGRADED · 0% of 16.6 GB", "warn": True}]}
    pool = {"source": "nas", "title": "nas tank is DEGRADED"}
    cert = {"source": "certs", "title": "Certificate expires in 3 days: example.org"}
    items = attention_items(None, {"rows": []}, storage, (), [pool, cert])
    assert items == [("storage", "Storage", "nas tank: DEGRADED · 0% of 16.6 GB", "/alerts", "Details"),
                     ("alerts", "Alerts", "Certificate expires in 3 days: example.org", "/alerts", "Review")]

    full = {"rows": [{"name": "nas tank", "detail": "ONLINE · 93% of 16.6 GB", "warn": True}]}
    assert attention_items(None, {"rows": []}, full, (), [])[0][3] == "/overview"     # no alert to open
    healthy = {"rows": [{"name": "nas tank", "detail": "ONLINE", "warn": False}]}
    assert attention_items(None, {"rows": []}, healthy, (), [pool])[0][0] == "alerts"  # not shown twice, not hidden


def test_ai_checkup_card_hidden_while_no_ai(monkeypatch):
    from lanxang.web import home_page, render
    monkeypatch.setattr(render, "AI_ON", False)
    assert home_page._analysis_card(None, None) == ""
    monkeypatch.setattr(render, "AI_ON", True)
    assert "Latest AI check-up" in home_page._analysis_card(None, None)


def test_flagged_card_dot_matches_its_border():
    from lanxang.web.home_page import _card
    html = _card("/x", "Security posture", "ok", "<p/>", flagged=True)
    assert 'class="dot warn"' in html and "hcard warn" in html


from datetime import datetime, timedelta

import pytest

NOW = datetime(2026, 11, 19, 12, 0)


@pytest.mark.parametrize("cookie, expected", [
    (None, NOW - timedelta(hours=24)),
    ("garbage", NOW - timedelta(hours=24)),
    (f"{NOW - timedelta(hours=2)}|{NOW - timedelta(minutes=10)}", NOW - timedelta(hours=2)),     # the same visit
    (f"{NOW - timedelta(days=2)}|{NOW - timedelta(hours=3)}", NOW - timedelta(hours=3)),         # a new visit
    (f"{NOW - timedelta(days=30)}|{NOW - timedelta(days=20)}", NOW - timedelta(days=7)),         # capped at 7 days
    (f"{NOW + timedelta(hours=1)}|{NOW + timedelta(hours=1)}", NOW - timedelta(hours=24)),       # from the future
])
def test_since_window(cookie, expected):
    from lanxang.web.home_page import since_window

    since, value = since_window(cookie, NOW)
    assert since == expected
    assert value.endswith("|2026-11-19T12:00") and " " not in value and ";" not in value and "," not in value


def _briefing(**extra):
    from lanxang.web.home_page import build_vitals

    vitals = build_vitals([{"source": "lan", "started_at": "2026-11-19T11:50:00", "ok": True, "error": "",
                            "seen_count": 12}], None, None, None, None, POSTURE_OK, None)
    changes = [(NOW - timedelta(hours=1), "device", "New device: Galaxy-Tab (192.0.2.40)", "/devices"),
               (NOW - timedelta(hours=3), "check", "Cleared: Backup is late", "/alerts")]
    alert = {"source": "certs", "title": "Certificate expires in 3 days: example.org"}
    args = dict(open_alerts=[alert], changes=changes, since=NOW - timedelta(hours=5), vitals=vitals,
                last_scan=NOW - timedelta(minutes=10), now=NOW)
    args.update(extra)
    return render_home_page(POSTURE_OK, build_hosts(None, LOCAL, None), EVENTS, **args)


def test_home_briefing_order():
    from lanxang.web.home_page import _headline

    html = _briefing().split("<main", 1)[1]
    marks = ['class="hero', "Certificate expires in 3 days", "Since you were here", 'class="trend', 'class="hcard']
    spots = [html.index(mark) for mark in marks]
    assert spots == sorted(spots)
    assert 'class="checkrow' in html and 'href="/alerts">Review' in html
    title = re.search(r'<p class="hero-title">([^<]*)</p>', html).group(1)
    assert title == _headline([("alerts",)]) and "last scan 10 min ago" in html
    assert "Galaxy-Tab" in html and "Backup is late" in html and "2 changes" in html and 'href="/history' in html


def test_home_no_problems_hides_problem_rows():
    html = _briefing(open_alerts=[]).split("<main", 1)[1]
    assert 'class="hero ok"' in html and 'class="checkrow' not in html and "Needs attention" not in html


def test_home_nothing_changed_line():
    html = _briefing(changes=[])
    assert "Nothing changed since" in html and 'class="timeline"' not in html


def test_home_stale_scan_is_unknown():
    for last_scan in (NOW - timedelta(hours=3), None):
        html = _briefing(open_alerts=[], last_scan=last_scan, scan_minutes=15)
        hero = re.search(r'<section class="hero[^"]*">.*?</section>', html).group(0)
        assert 'class="hero unknown"' in hero and "No recent scan" in hero
        assert "All good" not in hero and "everything else is healthy" not in hero.lower()


def test_home_keeps_all_cards():
    trends = {"hours": [{"hour": f"2026-11-19T{h:02d}:00:00", "direct": h * 1000, "vpn": 5} for h in range(24)],
              "new_per_day": [{"day": f"2026-11-1{d}", "count": d} for d in range(3, 10)]}
    analysis = {"summary": "Fine", "model": "m", "created_at": "2026-11-19 06:00:00", "recommendations": []}
    dns = {"error": "", "info": {"kind": "Pi-hole", "blocking": True, "queries": 10, "blocked": 1, "percent": 10.0}}
    ha = {"error": "", "failures": 0, "info": {"version": "1", "offline": [], "batteries": [], "updates": []}}
    storage = {"rows": [{"name": "md0", "detail": "ok", "warn": False}], "state": "ok"}
    html = _briefing(trends=trends, analysis=analysis, dns=dns, ha=ha, storage=storage)
    for title in ("Security posture", "Host health", "Storage &amp; RAID", "Pi-hole", "Smart home",
                  "Latest AI check-up", "Security trends", "Recent activity"):
        assert f"{title}</h2>" in html or f"{title}<span" in html, title


def test_security_trends_has_axes(monkeypatch):
    from lanxang.config.models import DisplayConfig
    from lanxang.web import render
    from lanxang.web.home_page import _trends_card

    monkeypatch.setattr(render, "DISPLAY", DisplayConfig(clock="12h", time_zone="America/New_York"))
    trends = {"hours": [{"hour": f"2026-11-19T{h:02d}:00:00", "direct": h * 1e6, "vpn": 5e6} for h in range(24)],
              "new_per_day": [{"day": f"2026-11-1{d}", "count": d} for d in range(3, 10)]}
    html = _trends_card(trends)
    assert html.count('class="bars"') == 3
    assert "25.0 MB" in html and "0 B" in html                       # y values in the unit
    assert "AM" in html or "PM" in html                              # x labels in the viewer's own clock
    assert "Mon" in html and "Thu" in html                           # weekdays under the 7-day chart
    titles = re.findall(r"<title>([^<]*)</title>", html)
    assert titles and not any("UTC" in t for t in titles) and any("EST" in t for t in titles)


def test_vitals_without_history():
    from lanxang.web.home_page import build_vitals

    tiles = build_vitals([], None, None, None, None, POSTURE_OK, None)
    assert len(tiles) == 2 and "Devices" in tiles[0] and "Security" in tiles[1]
    assert "<polyline" not in "".join(tiles) and 'class="trend unknown"' in tiles[0]


def test_vitals_with_a_week():
    from lanxang.web.home_page import build_vitals

    runs = [{"source": "unifi", "started_at": "2026-11-18T10:00:00", "ok": True, "error": "", "seen_count": 3}] + [
        {"source": "lan", "started_at": f"2026-11-1{d}T10:00:00", "ok": True, "error": "", "seen_count": 30 + d}
        for d in range(3, 10)]
    ups = {"upses": {"rack": {"state": "battery", "charge": 80.0}}}
    tiles = build_vitals(runs, (True, 14.6), ["ok"] * 7, ["ok"] * 6 + ["bad"],
                         {"name": "tank", "points": [40, 41, 44], "size": 16e12}, POSTURE_OK, ups)
    labels = [re.search(r'class="lbl">(?:<span[^>]*>.*?</span>)?([^<]*)<', t).group(1) for t in tiles]
    assert labels == ["Devices online", "Internet", "Services, 7 days", "Storage", "Security", "Power"]
    assert ">39<" in tiles[0] and "<polyline" in tiles[0]             # the LAN runs, not UniFi's
    assert "15 ms" in tiles[1] and "7 of 7 days ok" in tiles[1]
    assert "6 of 7 days ok" in tiles[2] and 'class="trend attention"' in tiles[2]
    assert ">44<" in tiles[3] and "16.0 TB" in tiles[3]
    assert "On battery" in tiles[5] and 'class="trend attention"' in tiles[5]
    degraded = build_vitals(None, None, None, None, {"name": "rpool", "points": [30], "warn": True}, None, None)
    assert degraded[0].startswith('<a class="trend attention"') and "see Storage &amp; RAID" in degraded[0]


def test_day_states_find_outages_per_day():
    from lanxang.web.home_page import day_states

    fine = [(NOW - timedelta(days=1, minutes=m), True) for m in range(3)]
    blip = [(NOW - timedelta(days=3, minutes=5), False), (NOW - timedelta(days=3, minutes=4), True)]
    down = [(NOW - timedelta(days=5, minutes=m), False) for m in (3, 2)]
    assert day_states([fine + blip + down], 2, NOW) == ["none", "bad", "none", "ok", "none", "ok", "none"]
    assert day_states([], 2, NOW) == ["none"] * 7
    # ok only when every check reported that day; an outage is bad even when another check is silent
    silent = [(NOW - timedelta(days=5, minutes=1), True)]
    assert day_states([fine + down, silent], 2, NOW) == ["none", "bad", "none", "none", "none", "none", "none"]
    assert day_states([fine, fine], 2, NOW)[5] == "ok"


def test_day_states_count_an_outage_across_midnight():
    from lanxang.web.home_page import day_states

    midnight = datetime(2026, 11, 19)                       # NOW's day starts here (UTC display)
    rows = [(midnight + timedelta(minutes=m), m >= 2) for m in (-2, -1, 0, 1, 2)]   # 4 failures, 2 each side
    assert day_states([rows], 3, NOW)[-2:] == ["bad", "bad"]
    assert day_states([rows], 5, NOW)[-2:] == ["ok", "ok"]


def test_weak_wifi_row():
    from lanxang.web.home_page import _wifi, weak_wifi

    def device(i, name, signal, status="seen", state="known"):
        wifi = {"signal": signal, "band": "2.4 GHz", "ap": "Hall AP"}
        return {"id": i, "name": name, "status": status, "state": state,
                "sightings": [{"detail": {"unifi": {"wifi": wifi}}, "mac": None}]}

    devices = [device(1, "Tablet", -75), device(2, "TV", -60), device(3, "Old phone", -80, status="quiet"),
               device(4, "Plug", -82, state="ignored"), device(5, "Laptop", -71)]
    weak = weak_wifi(devices)
    assert [d["name"] for d in weak] == ["Tablet", "Laptop"]
    html = _wifi(weak)
    assert "2 devices have a weak Wi-Fi signal" in html and "Tablet -75 dBm, 2.4 GHz on Hall AP" in html
    assert 'href="/devices/1"' in _wifi(weak[:1]) and "Tablet has a weak Wi-Fi signal" in _wifi(weak[:1])
    assert _wifi([]) == "" and weak_wifi([device(6, "Ok", None)]) == []
    assert "or use 5 GHz" in html and "or use 5 GHz" not in _wifi([{**weak[0], "band": "5 GHz"}])


def test_day_states_follow_the_viewer_zone():
    from lanxang.config.models import DisplayConfig
    from lanxang.web.home_page import day_states

    late = [(datetime(2026, 11, 19, 2, 0), True)]          # 02:00 UTC is still the 18th in New York
    assert day_states([late], 2, NOW)[-1] == "ok"
    ny = DisplayConfig(time_zone="America/New_York")
    assert day_states([late], 2, NOW, display=ny)[-2:] == ["ok", "none"]


def test_services_tile_without_recent_data_is_unknown():
    from lanxang.web.home_page import build_vitals

    tile = build_vitals(None, None, None, ["ok"] * 4 + ["none"] * 3, None, None, None)[0]
    assert 'class="trend unknown"' in tile and "No recent data" in tile and "All up" not in tile


def test_home_uses_the_viewer_zone_with_browser_time():
    from lanxang.web.home_page import _trends_card, home_display

    assert home_display(None).time_zone == "browser"
    tokyo = home_display("Asia/Tokyo")
    assert tokyo.time_zone == "Asia/Tokyo"
    trends = {"hours": [{"hour": f"2026-11-19T{h:02d}:00:00", "direct": h, "vpn": 1} for h in range(24)],
              "new_per_day": [{"day": f"2026-11-1{d}", "count": d} for d in range(3, 10)]}
    utc, here = _trends_card(trends), _trends_card(trends, tokyo)
    assert "2026-11-19 05:00 UTC" in utc and "2026-11-19 14:00 JST" in here         # bar titles shift
    html = _briefing(viewer_zone="Asia/Tokyo", changes=[(datetime(2026, 11, 19, 11, 0), "check", "Cleared: x", "/alerts")])
    assert re.search(r"<time[^>]*>[^<]*20:00</time>", html)                            # 11:00 UTC is 20:00 in Tokyo


def test_storage_trend_largest_pool_then_host_paths():
    from lanxang.web.home_page import storage_trend

    def scan(alloc):
        return {"nodes": [{"zfs": [{"name": "rpool", "size": 100, "alloc": 5}, {"name": "tank", "size": 1000, "alloc": alloc}]}]}

    scans = [(NOW - timedelta(days=2), scan(400)), (NOW - timedelta(hours=1), scan(440))]
    assert storage_trend(scans, fresh_after=NOW - timedelta(minutes=45)) == {
        "name": "tank", "points": [40.0, 44.0], "size": 1000, "stale": True}
    samples = [(NOW, {"storage": {"media": 58.0, "backup": 12.0}})]
    assert storage_trend([(NOW, {"nodes": []})], samples)["name"] == "media"
    assert storage_trend([], []) is None


def test_home_failed_parts_unknown_unless_something_to_show():
    hero = lambda html: re.search(r'<section class="hero[^"]*">.*?</section>', html).group(0)

    quiet = hero(_briefing(open_alerts=[], failed=["posture", "alerts"]))
    assert 'class="hero unknown"' in quiet and "read posture / alerts" in quiet and "healthy" not in quiet
    loud = hero(_briefing(failed=["posture"]))                       # the certificate alert still wins
    assert 'class="hero attention"' in loud


def test_scan_state():
    from lanxang.web.home_page import scan_state

    def run(source, at, ok):
        return {"source": source, "started_at": f"2026-11-19T{at}:00", "ok": ok, "error": "", "seen_count": 1}

    assert scan_state([]) == (None, False)
    assert scan_state([run("lan", "11:00", True), run("lan", "11:15", False), run("dhcp", "11:20", False)]) == (
        datetime(2026, 11, 19, 11, 0), True)
    assert scan_state([run("lan", "11:15", False), run("dhcp", "11:20", True)]) == (datetime(2026, 11, 19, 11, 20), False)


def test_speed_and_busiest_device_cards():
    from lanxang.web.home_page import _speed_card, _traffic_card

    now = datetime(2026, 11, 20, 15, 0)
    speed = {"at": "2026-11-20T09:05:00", "down": 1880.5, "up": 940.0, "ping": 9, "error": None,
             "history": [{"down": 1880.5}, {"down": 1210.0}]}
    html = _speed_card(speed, now)
    assert "1880.5 Mb/s" in html and "940 Mb/s" in html and "9 ms" in html and "6 h ago" in html
    assert "Slowest, 30 days" in html and "1210 Mb/s" in html and 'href="/settings#speedtest"' in html
    failed = _speed_card({**speed, "down": None, "up": None, "ping": None, "error": "timed out", "history": []}, now)
    assert "timed out" in failed and "hcard warn" in failed and "Download" not in failed
    assert _speed_card(None, now) == "" and _speed_card({}, now) == ""
    card = _traffic_card([("NAS", 2.7e9), ("Desk PC", 9e8)])
    assert "NAS" in card and "2.7 GB" in card and "900.0 MB" in card and _traffic_card([]) == ""
