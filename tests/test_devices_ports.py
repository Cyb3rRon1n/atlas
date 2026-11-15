import socket
import struct
import xml.etree.ElementTree as ElementTree
from datetime import datetime
from types import SimpleNamespace

from atlas.config.models import AtlasConfig
from atlas.devices import ports as ports_module
from atlas.devices.ports import assess, host_listeners, port_label, probe, run, upnp_mappings
from atlas.posture.model import build_posture
from atlas.posture.store import PostureStore
from atlas.web.devices_pages import _open_ports
from atlas.wiring.unifi import parse_exposure

GW = "192.0.2.1"
NOW = datetime(2026, 11, 15, 12, 0)


def test_probe_and_labels():
    open_ports = {("192.0.2.10", 22), ("192.0.2.10", 445)}
    found = probe(["192.0.2.10", "192.0.2.11"], [22, 80, 445], check=lambda ip, port, t: (ip, port) in open_ports)
    assert found == {"192.0.2.10": [22, 445], "192.0.2.11": []}
    assert port_label(22) == "22 (SSH)" and "risky" in port_label(445) and port_label(4242) == "4242"


def test_host_listeners_skip_loopback():
    conn = lambda ip, port, status="LISTEN": SimpleNamespace(status=status, laddr=SimpleNamespace(ip=ip, port=port))
    assert host_listeners([conn("0.0.0.0", 22), conn("127.0.0.1", 5432), conn("::", 8096), conn("::1", 631),
                           conn("192.0.2.5", 8080, "ESTABLISHED")]) == [22, 8096]


def current(open_ports, listeners=(22,), forwards=(), upnp=False):
    return {"devices": {"7": {"name": "living-room-tv", "ip": "192.0.2.20", "open": list(open_ports)}},
            "listeners": list(listeners), "forwards": list(forwards), "upnp": upnp, "host": "server"}


def test_first_run_learns_then_new_ports_alert_once():
    texts, state = assess({}, current([80]))
    assert texts == []
    texts, state = assess(state, current([80, 23]))
    assert len(texts) == 1 and "living-room-tv" in texts[0] and "23 (telnet)" in texts[0] and "risky" in texts[0]
    texts, state = assess(state, current([80]))                       # closed again: quiet
    assert texts == []
    texts, state = assess(state, current([80, 23]))                   # reopened: already known
    assert texts == []


def test_device_seen_for_the_first_time_is_learned_quietly_and_offline_devices_are_kept():
    _, state = assess({}, current([80]))
    newcomer = current([80])
    newcomer["devices"]["9"] = {"name": "new-laptop", "ip": "192.0.2.30", "open": [22, 445]}
    texts, state = assess(state, newcomer)
    assert texts == [] and state["devices"]["9"]["known"] == [22, 445]
    away = current([])
    away["devices"] = {}
    _, state = assess(state, away)
    assert set(state["devices"]) == {"7", "9"}


def test_host_listener_forward_and_upnp_alerts():
    _, state = assess({}, current([], listeners=[22]))
    texts, state = assess(state, current([], listeners=[22, 8081]))
    assert len(texts) == 1 and "New listening port on server" in texts[0] and "8081" in texts[0]
    forward = {"protocol": "tcp", "external": 3074, "client": "192.0.2.40", "port": 3074, "description": "game"}
    texts, state = assess(state, current([], listeners=[22, 8081], forwards=[forward]))
    assert len(texts) == 1 and "New port opened to the internet" in texts[0] and "TCP 3074 → 192.0.2.40:3074" in texts[0]
    texts, state = assess(state, current([], listeners=[22, 8081], forwards=[forward], upnp=True))
    assert len(texts) == 1 and "UPnP was switched on" in texts[0]
    assert state["recent"][0]["text"].startswith("🌐 UPnP")


def test_unknown_router_and_listeners_keep_previous_state():
    _, state = assess({}, current([], forwards=[]))
    unknown = current([])
    unknown.update(forwards=None, listeners=None, upnp=None)
    texts, after = assess(state, unknown)
    assert texts == [] and after["forwards"] == state["forwards"] and after["upnp"] is False


def test_unifi_exposure_parsing():
    result = parse_exposure([{"name": "game", "dst_port": "3074", "fwd": "192.0.2.40", "fwd_port": "3074",
                              "proto": "tcp_udp", "enabled": True},
                             {"name": "old", "dst_port": "22", "fwd": "192.0.2.5", "fwd_port": "22", "enabled": False}],
                            [{"key": "usg", "upnp_enabled": False}])
    assert result["upnp"] is False and [f["protocol"] for f in result["forwards"]] == ["tcp", "udp"]


DESCRIPTION = f"""<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device><serviceList><service>
<serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType><controlURL>/ctl/IPConn</controlURL>
</service></serviceList></device></root>"""


def soap_entries(entries):
    def soap(control, service, action, arguments, timeout):
        assert control == f"http://{GW}:5000/ctl/IPConn"
        index = arguments["NewPortMappingIndex"]
        if index >= len(entries):
            raise OSError("HTTP Error 500: SpecifiedArrayIndexInvalid")
        external, client = entries[index]
        return ElementTree.fromstring(
            f"<r><NewExternalPort>{external}</NewExternalPort><NewProtocol>TCP</NewProtocol>"
            f"<NewInternalClient>{client}</NewInternalClient><NewInternalPort>{external}</NewInternalPort>"
            f"<NewPortMappingDescription>console</NewPortMappingDescription></r>")
    return soap


def test_upnp_mappings_from_the_gateway_only():
    fetch = lambda url: DESCRIPTION.encode()
    mappings = upnp_mappings(GW, locate=lambda gw, t: f"http://{GW}:5000/rootDesc.xml", fetch=fetch,
                             soap=soap_entries([(3074, "192.0.2.40")]))
    assert mappings == [{"external": 3074, "protocol": "TCP", "client": "192.0.2.40", "port": 3074,
                         "description": "console"}]
    assert upnp_mappings(GW, locate=lambda gw, t: None) is None                    # UPnP off
    assert upnp_mappings(GW, locate=lambda gw, t: "http://198.51.100.9/x.xml", fetch=fetch) is None   # not the gateway


def files(arp):
    route = ("Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
             f"eth0\t00000000\t{struct.unpack('<L', socket.inet_aton(GW))[0]:08X}\t0003\t0\t0\t0\t00000000\n"
             f"eth0\t{struct.unpack('<L', socket.inet_aton('192.0.2.0'))[0]:08X}\t00000000\t0001\t0\t0\t0\t00FFFFFF\n")
    table = "IP address HW type Flags HW address Mask Device\n" + "".join(
        f"{ip} 0x1 0x2 aa:bb:cc:00:00:{i:02x} * eth0\n" for i, ip in enumerate(arp))
    return lambda path: route if path.endswith("route") else table


def test_run_end_to_end_and_pages(temp_db):
    store, sent = PostureStore(temp_db), []
    devices = [{"id": 7, "name": "living-room-tv", "ip": "192.0.2.20"},
               {"id": 8, "name": "asleep-laptop", "ip": "192.0.2.21"},       # not in ARP: not probed
               {"id": 1, "name": "this-server", "ip": "192.0.2.5"}]          # local address: listeners instead
    opened = {("192.0.2.20", 80)}
    kwargs = dict(read=files(["192.0.2.20", "192.0.2.5"]), check=lambda ip, port, t: (ip, port) in opened,
                  listeners=lambda: [22], upnp=lambda gw: None, local_ips=lambda: {"192.0.2.5"}, send=sent.append)
    texts, state = run(AtlasConfig(), store, devices, NOW, **kwargs)
    assert texts == [] and state["probed"] == 1 and set(state["devices"]) == {"7"}
    opened.add(("192.0.2.20", 23))
    texts, state = run(AtlasConfig(), store, devices, NOW, **kwargs)
    assert len(sent) == 1 and "telnet" in sent[0] and state["recent"][0]["at"] == "2026-11-15T12:00"

    router = build_posture(store, NOW)["router"]
    assert router["forwards"] is None and "New open port" in router["recent"][0]["text"]
    page = _open_ports(state["devices"]["7"])
    assert "23 (telnet)" in page and "80 (web)" in page
    assert "Not checked yet" in _open_ports(None)


def test_port_watch_can_be_turned_off_via_config():
    assert AtlasConfig(security={"port_watch": False}).security.port_watch is False
    assert ports_module.RECENT_MAX >= 8
