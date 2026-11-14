from atlas.wiring.build import build_wiring
from atlas.wiring.unifi import parse_unifi

DEVICES = [  # same shapes as tests/test_wiring_unifi.py
    {"mac": "02:00:00:00:00:01", "name": "gateway", "model": "UCGF", "type": "udm", "ip": "192.0.2.1",
     "port_table": [{"port_idx": 1, "name": "Port 1", "up": True, "speed": 1000, "mac": "02:00:00:00:00:02"},
                    {"port_idx": 2, "name": "Port 2", "up": True, "speed": 1000, "mac": "02:00:00:00:00:06"},
                    {"port_idx": 3, "name": "Port 3", "up": True, "speed": 2500},
                    {"port_idx": 4, "name": "Port 4", "up": True, "speed": 2500},
                    {"port_idx": 5, "name": "Port 5", "up": True, "speed": 2500}],
     "last_uplink": {"type": "wire", "uplink_mac": "00:00:5e:00:53:99", "port_idx": 5}},
    {"mac": "02:00:00:00:00:03", "name": "ap-express", "model": "UX7", "type": "udm", "radio_table": [{}],
     "port_table": [{"port_idx": 1, "up": True, "speed": 2500}, {"port_idx": 2, "up": True, "speed": 2500}],
     "last_uplink": {"type": "wire", "uplink_mac": "02:00:00:00:00:01", "uplink_remote_port": 4, "port_idx": 2}},
    {"mac": "02:00:00:00:00:04", "name": "mesh-ap", "type": "uap",
     "last_uplink": {"type": "wireless", "uplink_mac": "02:00:00:00:00:03"}},
]
CLIENTS = [
    {"mac": "02:00:00:00:00:10", "is_wired": True, "hostname": "core-switch", "ip": "192.0.2.2",
     "sw_mac": "02:00:00:00:00:01", "sw_port": 2},
    {"mac": "00:00:5e:00:53:01", "is_wired": True, "hostname": "nas", "ip": "192.0.2.10",
     "sw_mac": "02:00:00:00:00:01", "sw_port": 1},                     # really behind core-switch gi5
] + [{"mac": f"00:00:5e:00:53:{40 + i:02x}", "is_wired": True, "hostname": f"tv-{i}",
      "sw_mac": "02:00:00:00:00:01", "sw_port": 3} for i in range(5)]    # unmanaged bridge on Port 3

SWITCH = {
    "name": "core-switch", "host": "192.0.2.2", "sys_name": "core-switch", "chassis_mac": "02:00:00:00:00:10",
    "weak_privacy": False,
    "ports": {"gi1": {"index": 49, "up": True, "speed": 1000, "alias": ""},
              "gi2": {"index": 50, "up": True, "speed": 1000, "alias": ""},
              "gi5": {"index": 53, "up": True, "speed": 1000, "alias": ""},
              "gi6": {"index": 54, "up": False, "speed": 0, "alias": ""}},
    "neighbors": [{"port": "gi1", "chassis_mac": "02:00:00:00:00:02", "chassis": "", "remote_port": "",
                   "remote_port_mac": "02:00:00:00:00:02", "remote_port_desc": "", "sys_name": "gateway"},
                  {"port": "gi2", "chassis_mac": "02:00:00:00:00:06", "chassis": "", "remote_port": "",
                   "remote_port_mac": "02:00:00:00:00:06", "remote_port_desc": "", "sys_name": "gateway"}],
    "fdb": [{"port": "gi1", "mac": f"00:00:5e:00:53:{40 + i:02x}", "vlan": 1} for i in range(5)]
           + [{"port": "gi5", "mac": "00:00:5e:00:53:01", "vlan": 1},
              {"port": "gi5", "mac": "bc:24:11:00:00:01", "vlan": 1}],
}
INVENTORY = [{"id": 7, "name": "nas", "kind": "server", "sightings": [{"mac": "00:00:5e:00:53:01"}]},
             {"id": 8, "name": "nas-guest", "kind": "other", "sightings": [{"mac": "bc:24:11:00:00:01"}]}]
CABLING = {"panels": [{"panel": "PP1", "port": 5, "switch": "core-switch", "switch_port": "gi5",
                       "label": "Rack - nas", "color": "blue"},
                      {"panel": "PP1", "port": 9, "switch": "core-switch", "switch_port": "gi30",
                       "label": "", "color": ""}],
           "ports": {"gateway:Port 3": {"label": "ISP Wi-Fi bridge", "color": "yellow"}}, "error": None}


def _build():
    return build_wiring([SWITCH], parse_unifi(DEVICES, CLIENTS), INVENTORY, CABLING)


def _link(snapshot, a_name, a_port):
    names = {n["id"]: n["name"] for n in snapshot["nodes"]}
    return [l for l in snapshot["links"] if names[l["a"]] == a_name and l["a_port"] == a_port]


def test_infrastructure_links():
    snap = _build()
    names = {n["id"]: n for n in snap["nodes"]}
    assert any(n["kind"] == "wan" for n in snap["nodes"])
    assert "mesh-ap" not in {n["name"] for n in snap["nodes"]}                 # wireless uplink: hidden
    express = _link(snap, "gateway", "Port 4")[0]
    assert names[express["b"]]["name"] == "ap-express" and express["b_port"] == "Port 2" and express["speed"] == 2500
    core = _link(snap, "gateway", "Port 1")[0]
    assert names[core["b"]]["name"] == "core-switch" and core["b_port"] == "gi1" and core["via"] == "lldp"


def test_hosts_from_fdb_with_guests_behind_and_patch():
    snap = _build()
    names = {n["id"]: n for n in snap["nodes"]}
    nas_link = _link(snap, "core-switch", "gi5")[0]
    nas = names[nas_link["b"]]
    assert nas["name"] == "nas" and nas["device_id"] == 7 and nas["behind"] == ["nas-guest"]
    assert nas_link["patch"] == "PP1-05" and nas_link["label"] == "Rack - nas" and nas_link["color"] == "blue"
    assert not _link(snap, "gateway", "Port 1")[0]["b"].startswith("h:")     # nas not placed on the gateway


def test_unmanaged_bridge_and_port_label():
    snap = _build()
    names = {n["id"]: n for n in snap["nodes"]}
    bridge_link = _link(snap, "gateway", "Port 3")[0]
    bridge = names[bridge_link["b"]]
    assert bridge["kind"] == "bridge" and bridge["name"] == "ISP Wi-Fi bridge" and len(bridge["behind"]) == 5
    assert bridge_link["color"] == "yellow"


def test_warnings_double_link_and_bad_panel():
    snap = _build()
    assert any("2 links between gateway and core-switch" in w for w in snap["warnings"])
    assert any("PP1-09: core-switch has no port gi30" in w for w in snap["warnings"])
    panel = next(p for p in snap["panels"] if p["port"] == 5)
    assert panel["device"] == "nas" and panel["speed"] == 1000 and panel["up"] is True


def test_snmp_only_no_unifi():
    snap = build_wiring([SWITCH], None, INVENTORY, {"panels": [], "ports": {}, "error": None})
    assert any(n["name"] == "nas" for n in snap["nodes"])
    assert all(n["kind"] != "wan" for n in snap["nodes"])

def test_hypervisor_with_guests_stays_a_host():
    switch = dict(SWITCH, fdb=[{"port": "gi5", "mac": "00:00:5e:00:53:01", "vlan": 1}]
                  + [{"port": "gi5", "mac": f"bc:24:11:00:00:0{i}", "vlan": 1} for i in range(1, 6)])
    snap = build_wiring([switch], None, INVENTORY, {"panels": [], "ports": {}, "error": None})
    host = next(n for n in snap["nodes"] if n["name"] == "nas")
    assert len(host["behind"]) == 5


def test_named_device_beats_unnamed_bmc_on_the_same_port():
    switch = dict(SWITCH, fdb=[{"port": "gi5", "mac": "00:00:5e:00:53:0b", "vlan": 1},
                               {"port": "gi5", "mac": "00:00:5e:00:53:01", "vlan": 1}])
    inventory = INVENTORY + [{"id": 9, "name": "192.0.2.98", "kind": "other",
                              "sightings": [{"mac": "00:00:5e:00:53:0b"}]}]
    snap = build_wiring([switch], None, inventory, {"panels": [], "ports": {}, "error": None})
    host = next(n for n in snap["nodes"] if n["kind"] == "host")
    assert host["name"] == "nas" and host["behind"] == ["192.0.2.98"]
