import subprocess

import pytest

from atlas.config.models import WiringSwitch
from atlas.wiring import WiringError
from atlas.wiring.snmp import OIDS, collect_switch, parse_switch, parse_walk, walk_switch

WALKS = {
    "sysName": ".1.3.6.1.2.1.1.5.0 = STRING: core-switch\n",
    "lldpLocChassis": ".1.0.8802.1.1.2.1.3.2.0 = Hex-STRING: 02 00 00 00 00 10 \n",
    "ifName": ".1.3.6.1.2.1.31.1.1.1.1.49 = STRING: gi1\n.1.3.6.1.2.1.31.1.1.1.1.50 = STRING: gi2\n"
              ".1.3.6.1.2.1.31.1.1.1.1.51 = STRING: gi3\n.1.3.6.1.2.1.31.1.1.1.1.7000 = STRING: loopback1\n",
    "ifOper": ".1.3.6.1.2.1.2.2.1.8.49 = INTEGER: up(1)\n.1.3.6.1.2.1.2.2.1.8.50 = INTEGER: up(1)\n"
              ".1.3.6.1.2.1.2.2.1.8.51 = INTEGER: down(2)\n.1.3.6.1.2.1.2.2.1.8.7000 = INTEGER: up(1)\n",
    "ifHighSpeed": ".1.3.6.1.2.1.31.1.1.1.15.49 = Gauge32: 1000\n.1.3.6.1.2.1.31.1.1.1.15.50 = Gauge32: 1000\n"
                   ".1.3.6.1.2.1.31.1.1.1.15.51 = Gauge32: 0\n",
    "ifAlias": ".1.3.6.1.2.1.31.1.1.1.18.49 = STRING: uplink\n.1.3.6.1.2.1.31.1.1.1.18.50 = STRING: \n",
    "basePort": ".1.3.6.1.2.1.17.1.4.1.2.49 = INTEGER: 49\n.1.3.6.1.2.1.17.1.4.1.2.50 = INTEGER: 50\n"
                ".1.3.6.1.2.1.17.1.4.1.2.51 = INTEGER: 51\n",
    # vlan 1; MACs 02:00:00:00:00:01 on gi1 (the gateway side) and 00:00:5e:00:53:01 on gi2
    "qFdb": ".1.3.6.1.2.1.17.7.1.2.2.1.2.1.2.0.0.0.0.1 = INTEGER: 49\n"
            ".1.3.6.1.2.1.17.7.1.2.2.1.2.1.0.0.94.0.83.1 = INTEGER: 50\n",
    "dFdb": "",
    # neighbour on local port 49: chassis given as a MAC string, port id as Hex-STRING
    "lldpRem": ".1.0.8802.1.1.2.1.4.1.1.5.0.49.3 = STRING: 02:00:00:00:00:01\n"
               ".1.0.8802.1.1.2.1.4.1.1.7.0.49.3 = Hex-STRING: 02 00 00 00 00 02 \n"
               ".1.0.8802.1.1.2.1.4.1.1.8.0.49.3 = STRING: Port 1\n"
               ".1.0.8802.1.1.2.1.4.1.1.9.0.49.3 = STRING: gateway\n"
               ".1.0.8802.1.1.2.1.4.1.1.5.0.50.4 = Hex-STRING: 00 00 5E 00 53 01 \n"
               ".1.0.8802.1.1.2.1.4.1.1.7.0.50.4 = STRING: eth0\n"
               ".1.0.8802.1.1.2.1.4.1.1.9.0.50.4 = STRING: \n",
}


def test_parse_walk_strips_types_and_joins_continuations():
    text = ".1.2.3.1 = STRING: \"a b\"\n.1.2.3.2 = Hex-STRING: 01 02\n03 04\n.1.2.3.3 = No Such Object available\n"
    assert parse_walk(text, "1.2.3") == {"1": "a b", "2": "01 02 03 04"}


def test_parse_switch():
    result = parse_switch(WALKS)
    assert result["sys_name"] == "core-switch" and result["chassis_mac"] == "02:00:00:00:00:10"
    assert set(result["ports"]) == {"gi1", "gi2", "gi3"}            # loopback is not a bridge port
    assert result["ports"]["gi1"] == {"index": 49, "up": True, "speed": 1000, "alias": "uplink"}
    assert result["ports"]["gi3"]["up"] is False
    assert {"port": "gi2", "mac": "00:00:5e:00:53:01", "vlan": 1} in result["fdb"]
    gateway = next(n for n in result["neighbors"] if n["port"] == "gi1")
    assert gateway["chassis_mac"] == "02:00:00:00:00:01" and gateway["remote_port_mac"] == "02:00:00:00:00:02"
    assert gateway["remote_port_desc"] == "Port 1" and gateway["sys_name"] == "gateway"
    host = next(n for n in result["neighbors"] if n["port"] == "gi2")
    assert host["chassis_mac"] == "00:00:5e:00:53:01" and host["remote_port"] == "eth0"


def test_parse_switch_falls_back_to_dot1d_fdb():
    walks = dict(WALKS, qFdb="", dFdb=".1.3.6.1.2.1.17.4.3.1.2.0.0.94.0.83.1 = INTEGER: 50\n")
    assert parse_switch(walks)["fdb"] == [{"port": "gi2", "mac": "00:00:5e:00:53:01", "vlan": None}]


SWITCH = WiringSwitch(name="core-switch", host="192.0.2.2", priv="des")
ENV = {"ATLAS_SNMP_CORE_SWITCH_AUTH": "auth-secret-123", "ATLAS_SNMP_CORE_SWITCH_PRIV": "priv-secret-456"}


def test_walk_switch_keeps_secrets_off_the_command_line(tmp_path):
    seen = []

    def fake_run(args, **kwargs):
        conf = (kwargs["env"]["SNMPCONFPATH"] + "/snmp.conf")
        seen.append((args, open(conf).read()))
        key = next(k for k, oid in OIDS.items() if oid == args[-1])
        return subprocess.CompletedProcess(args, 0, WALKS.get(key, ""), "")

    walks = walk_switch(SWITCH, ENV, 5, run=fake_run, which=lambda _: "/usr/bin/snmpbulkwalk")
    assert walks["ifName"] == WALKS["ifName"]
    for args, conf in seen:
        assert "auth-secret-123" not in " ".join(args) and "priv-secret-456" not in " ".join(args)
        assert "defAuthPassphrase auth-secret-123" in conf and "defPrivType DES" in conf
    assert not any(k == "dFdb" for k in walks if walks[k])     # qFdb answered, so dFdb was skipped


def test_walk_switch_errors():
    with pytest.raises(WiringError, match="install net-snmp"):
        walk_switch(SWITCH, ENV, 5, which=lambda _: None)
    with pytest.raises(WiringError, match="ATLAS_SNMP_CORE_SWITCH_AUTH"):
        walk_switch(SWITCH, {}, 5, which=lambda _: "/x")

    def failing(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "Timeout: No Response from 192.0.2.2\n")
    with pytest.raises(WiringError, match="Timeout"):
        walk_switch(SWITCH, ENV, 5, run=failing, which=lambda _: "/x")


def test_collect_switch_marks_des_weak():
    def fake_run(args, **kwargs):
        key = next(k for k, oid in OIDS.items() if oid == args[-1])
        return subprocess.CompletedProcess(args, 0, WALKS.get(key, ""), "")
    result = collect_switch(SWITCH, ENV, 5, run=fake_run, which=lambda _: "/x")
    assert result["name"] == "core-switch" and result["weak_privacy"] is True