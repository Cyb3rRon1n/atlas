import copy
from datetime import datetime, timedelta

from lanxang.config.models import AtlasConfig
from lanxang.web.cabling_page import render_cabling_page
from lanxang.wiring import traffic
from lanxang.wiring.scan import run_scan
from lanxang.wiring.store import WiringStore


def switch(in_bytes, out_bytes, speed=1000):
    return {"name": "core-switch", "host": "192.0.2.2", "sys_name": "core-switch", "chassis_mac": "02:00:00:00:00:10",
            "ports": {"gi5": {"index": 53, "up": True, "speed": speed, "alias": "",
                              "counters": {"in_bytes": in_bytes, "out_bytes": out_bytes}}},
            "neighbors": [], "fdb": [{"port": "gi5", "mac": "00:00:5e:00:53:01", "vlan": 1}]}


def raw(*args, **kwargs):
    return {"switches": {"core-switch": switch(*args, **kwargs)}, "unifi": None}


def test_rates_are_bits_per_second_and_skip_resets_and_stale():

    assert traffic.rates(raw(1_000, 2_000), raw(0, 0), 8) == {("core-switch", "gi5"): (1000.0, 2000.0)}
    assert traffic.rates(raw(10, 0), raw(500, 0), 8) == {}                      # counter reset: no fake spike
    assert traffic.rates(raw(None, 0), raw(0, 0), 8) == {}                      # switch doesn't report bytes
    assert traffic.rates(raw(1_000, 0), raw(0, 0), 8, stale={"core-switch"}) == {}
    assert traffic.rates(raw(1_000, 0), raw(0, 0), 0) == {}
    assert traffic.text(940_000_000) == "940 Mb/s" and traffic.text(1_250_000) == "1.2 Mb/s"


def test_scan_puts_load_on_the_cable_and_keeps_a_week(temp_db, tmp_path):

    settings = AtlasConfig(wiring={"enabled": True, "cabling_file": str(tmp_path / "cabling.yaml"),
                                   "switches": [{"name": "core-switch", "host": "192.0.2.2"}]})
    start = datetime(2026, 1, 1, 12)
    run_scan(settings, WiringStore(), [], env={}, now=start, collect=lambda *a, **k: switch(0, 0))
    # 900 s at 600 Mbit/s in = 67.5 GB
    result = run_scan(settings, WiringStore(), [], env={}, now=start + timedelta(seconds=900),
                      collect=lambda *a, **k: switch(67_500_000_000, 1_000))
    link = next(link for link in result["snapshot"]["links"] if link["a_port"] == "gi5")
    assert link["bps"] == 600e6 and link["load"] == 0.6

    history = traffic.history(WiringStore().engine, start)
    assert history[("core-switch", "gi5")][0][1:] == (600e6, 8_000 / 900)
    traffic.save(WiringStore().engine, {("core-switch", "gi5"): (1.0, 1.0)}, start + timedelta(days=8))
    assert len(traffic.history(WiringStore().engine, start)[("core-switch", "gi5")]) == 1   # week-old row pruned


def test_page_shows_busy_cable_and_graph(temp_db, tmp_path):

    settings = AtlasConfig(wiring={"enabled": True, "cabling_file": str(tmp_path / "cabling.yaml"),
                                   "switches": [{"name": "core-switch", "host": "192.0.2.2"}]})
    start = datetime(2026, 1, 1, 12)
    for step, total in enumerate((0, 45_000_000_000, 99_000_000_000)):
        run_scan(settings, WiringStore(), [], env={}, now=start + timedelta(seconds=900 * step),
                 collect=lambda *a, total=total, **k: switch(total, 0))
    latest = WiringStore().latest(1)[0]
    page = render_cabling_page(latest, [], True, now=start + timedelta(hours=1),
                               history=traffic.history(WiringStore().engine, start))

    assert '"load": 0.48' in page                                   # map data carries the load
    assert 'class="spark' in page and "24 h peak 480 Mb/s (48% of the link)" in page
    assert "480 Mb/s</td>" in page
    plain = render_cabling_page(copy.deepcopy(latest), [], True, now=start + timedelta(hours=1))
    assert 'class="spark' not in plain                              # no history: no graph, page still renders


def test_top_users_names_wired_devices_by_data_moved():

    snapshot = {"nodes": [{"id": "s:core", "name": "core", "kind": "switch"}, {"id": "h:pc", "name": "Desk PC", "kind": "host"},
                          {"id": "h:nas", "name": "NAS", "kind": "host"}, {"id": "a:ap", "name": "Hall AP", "kind": "ap"}],
                "links": [{"a": "s:core", "a_port": "gi1", "b": "h:pc", "b_port": ""},
                          {"a": "s:core", "a_port": "gi2", "b": "h:nas", "b_port": ""},
                          {"a": "s:core", "a_port": "gi3", "b": "h:nas", "b_port": ""},
                          {"a": "s:core", "a_port": "gi4", "b": "a:ap", "b_port": ""}]}
    t = datetime(2026, 11, 20, 12, 0)
    later = t + timedelta(minutes=15)
    history = {("core", "gi1"): [(t, 0, 0), (later, 8e6, 0)],                 # 1 MB/s for 900 s
               ("core", "gi2"): [(t, 0, 0), (later, 8e6, 8e6)],               # a two-port bond: both count
               ("core", "gi3"): [(t, 0, 0), (later, 8e6, 0)],
               ("core", "gi4"): [(t, 0, 0), (later, 8e9, 0)],                 # an access point carries everyone
               ("core", "gi9"): [(t, 0, 0), (later, 8e9, 0)],                 # nothing known on this port
               ("core", "gi1x"): [(t, 0, 0)]}
    top = traffic.top_users(history, snapshot)
    assert top == [("NAS", 2.7e9), ("Desk PC", 9e8)]
    assert traffic.top_users(history, snapshot, n=1) == [("NAS", 2.7e9)]
    gap = {("core", "gi1"): [(t, 0, 0), (t + timedelta(hours=6), 8e6, 0)]}    # scanner off for hours: capped at 2 h
    assert traffic.top_users(gap, snapshot) == [("Desk PC", 7.2e9)]
