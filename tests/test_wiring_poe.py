import copy
from datetime import datetime

from lanxang.web.cabling_page import render_cabling_page
from lanxang.wiring.health import alerts, assess, poe_ports
from lanxang.wiring.snmp import parse_switch
from lanxang.wiring.store import diff_snapshots
from lanxang.wiring.unifi import parse_unifi
from tests.test_web_cabling import _latest
from tests.test_wiring_snmp import WALKS

# POWER-ETHERNET-MIB as net-snmp prints it with MIBS="": gi1 (ifIndex 49) powering a class 4 device,
# gi2 searching (PoE on, nothing attached), gi3 a fault; one PSE group with a 370 W budget, 61 W used.
POE_WALKS = {
    "psePort": "".join(f".1.3.6.1.2.1.105.1.1.1.{col}.1.{port} = INTEGER: {value}\n"
                       for port, values in {49: (1, 3, 5), 50: (1, 2, 1), 51: (1, 4, 1)}.items()
                       for col, value in zip((3, 6, 10), values)),
    "pseMain": ".1.3.6.1.2.1.105.1.3.1.1.2.1 = Gauge32: 370\n.1.3.6.1.2.1.105.1.3.1.1.4.1 = Gauge32: 61\n",
}


def test_snmp_poe_per_port_and_budget():
    switch = parse_switch({**WALKS, **POE_WALKS})
    ports = switch["ports"]
    assert ports["gi1"]["poe"] == {"delivering": True, "fault": False, "enabled": True, "watts": None,
                                   "mode": "delivering", "class": "Class 4"}
    assert ports["gi2"]["poe"]["delivering"] is False and ports["gi2"]["poe"]["mode"] == "searching"
    assert ports["gi3"]["poe"]["fault"] is True
    assert (switch["poe_budget_w"], switch["poe_used_w"]) == (370, 61)


def test_switch_without_poe_has_none():
    switch = parse_switch(WALKS)
    assert not any("poe" in port for port in switch["ports"].values())
    assert switch["poe_budget_w"] is None


def unifi_gateway(poe_power="0.00", enable=False):
    return parse_unifi([{"mac": "02:00:00:00:00:01", "name": "gateway", "type": "udm", "total_max_power": 30,
                         "port_table": [{"port_idx": 1, "name": "Port 1", "up": True, "port_poe": False},
                                        {"port_idx": 4, "name": "Port 4", "up": True, "port_poe": True,
                                         "poe_mode": "auto", "poe_enable": enable, "poe_power": poe_power,
                                         "poe_class": "Class 4", "poe_caps": 3}]}], [])


def test_unifi_poe_ports_and_budget():
    idle = unifi_gateway()["devices"][0]
    assert "poe" not in idle["ports"]["Port 1"]
    assert idle["ports"]["Port 4"]["poe"]["delivering"] is False and idle["poe_budget_w"] == 30
    busy = unifi_gateway("6.20", True)["devices"][0]
    assert busy["ports"]["Port 4"]["poe"]["watts"] == 6.2 and busy["poe_used_w"] == 6.2


def raw_switch(walks):
    switch = parse_switch(walks)
    return {"switches": {"core-switch": {**switch, "name": "core-switch"}}, "unifi": None}


def test_fault_alerts_and_budget_is_watch_only():
    raw = raw_switch({**WALKS, **POE_WALKS})
    issues = [i for i in assess(raw, []) if i["kind"].startswith("poe")]
    assert {(i["kind"], i["level"], i["port"]) for i in issues} == {("poe_fault", "bad", "gi3")}
    texts = alerts([], issues)
    assert len(texts) == 1 and "PoE fault: core-switch gi3" in texts[0]
    full = dict(POE_WALKS, pseMain=".1.3.6.1.2.1.105.1.3.1.1.2.1 = Gauge32: 30\n"
                                   ".1.3.6.1.2.1.105.1.3.1.1.4.1 = Gauge32: 28\n")
    budget = [i for i in assess(raw_switch({**WALKS, **full}), []) if i["kind"] == "poe_budget"]
    assert budget[0]["level"] == "watch" and "28 W of 30 W" in budget[0]["detail"]
    assert assess(raw, [], stale={"core-switch"}) == []


def test_poe_start_and_stop_show_as_changes():
    before = {"nodes": [], "links": [], "poe": poe_ports({"switches": {}, "unifi": unifi_gateway()})}
    after = {"nodes": [], "links": [], "poe": poe_ports({"switches": {}, "unifi": unifi_gateway("6.20", True)})}
    assert [c["text"] for c in diff_snapshots(before, after)] == ["gateway Port 4 started delivering PoE"]
    assert [c["text"] for c in diff_snapshots(after, before)] == ["gateway Port 4 stopped delivering PoE"]
    assert diff_snapshots({"nodes": [], "links": []}, after) == []      # snapshot from before PoE existed


def test_faceplate_marks_powered_and_capable_ports():
    latest = _latest()
    switch = latest["raw"]["switches"]["core-switch"] = copy.deepcopy(latest["raw"]["switches"]["core-switch"])
    port = next(iter(switch["ports"]))
    switch["ports"][port]["poe"] = {"delivering": True, "fault": False, "enabled": True, "watts": 6.5,
                                    "mode": "auto", "class": "Class 4"}
    switch["poe_budget_w"], switch["poe_used_w"] = 30, 6.5
    page = render_cabling_page(latest, [], True, now=datetime(2026, 1, 1, 13))
    assert 'class="port poe ' in page and "PoE 6.5 W Class 4" in page
    assert f"· PoE: {port} (1 powering, 6.5 W of 30 W)" in page
    switch["ports"][port]["poe"].update(delivering=False, watts=0.0)
    switch["poe_used_w"] = 0.0
    page = render_cabling_page(latest, [], True, now=datetime(2026, 1, 1, 13))
    assert 'class="port poe-cap ' in page and "PoE capable, not powering (auto)" in page
    assert f"· PoE: {port} (none powering, 0 W of 30 W)" in page
    assert "· PoE:" not in render_cabling_page(_latest(), [], True, now=datetime(2026, 1, 1, 13))
