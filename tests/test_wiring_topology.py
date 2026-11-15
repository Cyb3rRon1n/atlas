import copy

from atlas.config.models import AtlasConfig
from atlas.web.cabling_page import render_cabling_page
from atlas.wiring.build import build_wiring
from atlas.wiring.scan import run_scan
from atlas.wiring.snmp import parse_switch
from atlas.wiring.store import WiringStore
from atlas.wiring.unifi import parse_unifi
from tests.test_web_cabling import _latest
from tests.test_wiring_build import CABLING, CLIENTS, DEVICES, INVENTORY, SWITCH
from tests.test_wiring_snmp import WALKS

# Model, spanning tree, a port-channel and VLANs as net-snmp prints them with MIBS="".
# gi1 (bridge port 49) forwards, gi2 (50) is blocked; gi3 and gi4 (ifIndex 51/52) are in Po1 (ifIndex 1000) -
# gi4 is not a bridge port (the port-channel took its place); every port is on VLAN 1 untagged and gi1+gi2
# also carry VLAN 20 tagged (bridge ports 49/50 = byte 7, bits 0x80 and 0x40).
TOPOLOGY_WALKS = {
    **WALKS,
    "ifName": WALKS["ifName"] + ".1.3.6.1.2.1.31.1.1.1.1.52 = STRING: gi4\n.1.3.6.1.2.1.31.1.1.1.1.1000 = STRING: Po1\n",
    "sysDescr": '.1.3.6.1.2.1.1.1.0 = STRING: "ACME-28 28-Port Gigabit Managed Switch"\n',
    "stp": ".1.3.6.1.2.1.17.2.15.1.3.49 = INTEGER: 5\n.1.3.6.1.2.1.17.2.15.1.3.50 = INTEGER: 2\n",
    "lag": "".join(f".1.2.840.10006.300.43.1.2.1.1.13.{i} = INTEGER: {agg}\n"
                   for i, agg in ((49, 49), (50, 50), (51, 1000), (52, 1000))),
    "pvid": "".join(f".1.3.6.1.2.1.17.7.1.4.5.1.1.{i} = Gauge32: 1\n" for i in (49, 50, 51)),
    "vlanEgress": ".1.3.6.1.2.1.17.7.1.4.2.1.4.0.1 = Hex-STRING: 00 00 00 00 00 00 E0 00 \n"
                  ".1.3.6.1.2.1.17.7.1.4.2.1.4.0.20 = Hex-STRING: 00 00 00 00 00 00 C0 00 \n",
    "vlanUntagged": ".1.3.6.1.2.1.17.7.1.4.2.1.5.0.1 = Hex-STRING: 00 00 00 00 00 00 E0 00 \n"
                    ".1.3.6.1.2.1.17.7.1.4.2.1.5.0.20 = Hex-STRING: 00 00 00 00 00 00 00 00 \n",
}


def test_snmp_model_stp_lag_and_vlans():
    switch = parse_switch(TOPOLOGY_WALKS)
    ports = switch["ports"]
    assert switch["model"] == "ACME-28 28-Port Gigabit Managed Switch"
    assert ports["gi1"]["stp"] == "forwarding" and ports["gi2"]["stp"] == "blocking"
    assert ports["gi3"]["lag"] == "Po1" and ports["gi4"]["lag"] == "Po1" and "lag" not in ports["gi1"]
    assert ports["gi1"]["vlan"] == 1 and ports["gi1"]["tagged"] == [20] and "tagged" not in ports["gi3"]


def test_switch_without_the_tables_shows_nothing_new():
    switch = parse_switch(WALKS)
    assert switch["model"] == ""
    assert not any(key in port for port in switch["ports"].values() for key in ("stp", "lag", "vlan", "tagged"))


def test_unifi_stp_state_and_bundle():
    gateway = parse_unifi([{"mac": "02:00:00:00:00:01", "name": "gw", "type": "udm",
                            "port_table": [{"port_idx": 1, "up": True, "stp_state": "forwarding"},
                                           {"port_idx": 2, "up": True, "aggregated_by": 1},
                                           {"port_idx": 3, "up": True, "aggregated_by": False}]}], [])
    ports = gateway["devices"][0]["ports"]
    assert ports["Port 1"]["stp"] == "forwarding" and ports["Port 1"]["lag"] == "LAG 1"
    assert ports["Port 2"]["lag"] == "LAG 1" and "lag" not in ports["Port 3"]


def _with(states=None, lag=None):
    switch = copy.deepcopy(SWITCH)
    for port, state in (states or {}).items():
        switch["ports"][port]["stp"] = state
    if lag:
        for port in ("gi1", "gi2"):
            switch["ports"][port]["lag"] = lag
    return switch


def _snapshot(switch):
    return build_wiring([switch], parse_unifi(DEVICES, CLIENTS), INVENTORY, CABLING)


def _pair(snapshot):
    names = {n["id"]: n["name"] for n in snapshot["nodes"]}
    return [l for l in snapshot["links"] if {names[l["a"]], names[l["b"]]} == {"gateway", "core-switch"}]


def test_backup_cable_on_standby_is_a_note_not_a_warning():
    snap = _snapshot(_with({"gi1": "forwarding", "gi2": "blocking"}))
    assert not any("core-switch" in w and "gateway" in w for w in snap["warnings"]) and snap["loops"] == []
    assert any("gi2 is on standby" in note for note in snap["notes"])
    assert {l["b_port"]: l["standby"] for l in _pair(snap)} == {"gi1": False, "gi2": True}


def test_both_cables_forwarding_is_a_loop():
    snap = _snapshot(_with({"gi1": "forwarding", "gi2": "forwarding"}))
    assert any(w.startswith("Loop risk: 2 cables between gateway and core-switch") for w in snap["warnings"])
    assert snap["loops"] == ["core-switch ⇄ gateway"]


def test_bundled_cables_are_fine():
    snap = _snapshot(_with(lag="Po1"))
    assert snap["loops"] == [] and any("bundled as Po1" in note for note in snap["notes"])
    assert {l["lag"] for l in _pair(snap)} == {"Po1"}


def test_no_spanning_tree_data_keeps_the_old_warning():
    snap = _snapshot(_with())
    assert any("2 links between gateway and core-switch" in w for w in snap["warnings"]) and snap["loops"] == []


def test_loop_alerts_once_then_resolves(temp_db, tmp_path):
    settings = AtlasConfig(wiring={"enabled": True, "cabling_file": str(tmp_path / "cabling.yaml"),
                                   "unifi": {"enabled": True, "url": "https://192.0.2.1"},
                                   "switches": [{"name": "core-switch", "host": "192.0.2.2"}]})
    unifi = lambda *a, **k: parse_unifi(DEVICES, CLIENTS)
    sent = []

    def scan(states):
        run_scan(settings, WiringStore(), [], env={}, collect=lambda *a, **k: _with(states), fetch=unifi,
                 send=sent.append)

    scan({"gi1": "forwarding", "gi2": "blocking"})
    scan({"gi1": "forwarding", "gi2": "forwarding"})
    scan({"gi1": "forwarding", "gi2": "forwarding"})
    assert len(sent) == 1 and "Possible network loop: core-switch ⇄ gateway" in sent[0]
    scan({"gi1": "forwarding", "gi2": "blocking"})
    assert len(sent) == 2 and "Resolved" in sent[1]


def test_page_shows_standby_model_and_vlan_filter():
    latest = _latest()
    switch = _with({"gi1": "forwarding", "gi2": "blocking"})
    switch["model"] = "ACME-28 28-Port Gigabit Managed Switch"
    switch["ports"]["gi5"].update(vlan=10)
    switch["ports"]["gi1"].update(vlan=1)
    latest["raw"]["switches"]["core-switch"] = switch
    latest["snapshot"] = _snapshot(switch)
    page = render_cabling_page(latest, [], True)
    assert "· ACME-28 28-Port Gigabit Managed Switch" in page and 'class="notes"' in page
    assert "standby up" in page and "spanning tree: blocking (standby)" in page
    assert 'id="vlan-filter"' in page and 'data-vlans="10"' in page
    single = render_cabling_page(_latest(), [], True)
    assert 'id="vlan-filter"' not in single
