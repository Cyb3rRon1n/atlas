import socket
import threading

from lanxang.config.models import AtlasConfig
from lanxang.devices import snmpprobe
from lanxang.wiring.snmp import _caps
from lanxang.wiring.suggest import suggestions
from lanxang.web.settings_page import handle_post


def _report(engine):
    """A minimal SNMPv3 Report as an agent sends back to discovery."""

    t = snmpprobe._tlv
    usm = t(0x30, snmpprobe._octets(engine) + snmpprobe._int(1) + snmpprobe._int(5) + snmpprobe._octets(b"")
            + snmpprobe._octets(b"") + snmpprobe._octets(b""))
    header = t(0x30, snmpprobe._int(7) + snmpprobe._int(65507) + snmpprobe._octets(b"\x00") + snmpprobe._int(3))
    return t(0x30, snmpprobe._int(3) + header + snmpprobe._octets(usm) + t(0x30, b""))


def test_discovery_packet_has_no_user_and_reads_the_engine_id():
    packet = snmpprobe.discovery_packet(1234)
    assert packet[0] == 0x30 and b"\x04\x01\x04" in packet           # reportable, noAuthNoPriv
    engine = bytes.fromhex("80000009030000005e0001")
    assert snmpprobe.engine_id(_report(engine)) == engine
    assert snmpprobe.vendor(engine) == "Cisco" and snmpprobe.vendor(bytes.fromhex("8000a09804")) == "Ubiquiti"
    assert snmpprobe.engine_id(b"\x30\x03\x02\x01\x01") is None and snmpprobe.engine_id(b"junk") is None


def test_discover_over_a_real_socket():
    agent = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    agent.bind(("127.0.0.1", 0))

    def answer():
        data, addr = agent.recvfrom(4096)
        assert snmpprobe.engine_id(data) is None                     # discovery carries an empty engine ID
        agent.sendto(_report(bytes.fromhex("800000ab03aabbcc")), addr)

    threading.Thread(target=answer, daemon=True).start()
    found = snmpprobe.discover(["127.0.0.1"], timeout=2, port=agent.getsockname()[1])
    agent.close()
    assert found == {"127.0.0.1": {"engine": "800000ab03aabbcc", "vendor": "D-Link"}}


def test_lldp_capabilities():
    assert _caps("28 00") == ["bridge", "router"] and _caps("(") == ["bridge", "router"]
    assert _caps("20 00") == ["bridge"] and _caps("") == []


DEVICES = [
    {"id": 1, "name": "office-switch", "ip": "192.0.2.20", "sightings": [{"mac": "aa:bb:cc:00:00:20"}]},
    {"id": 2, "name": "nas", "ip": "192.0.2.30", "sightings": []},
    {"id": 3, "name": "core", "ip": "192.0.2.2", "sightings": []},
]


def test_suggestions_combine_signals_and_skip_known_or_dismissed():
    settings = AtlasConfig(wiring={"switches": [{"name": "core", "host": "192.0.2.2"}], "not_managed": ["192.0.2.40"]})
    ports = {"snmp": {"192.0.2.20": {"vendor": "Netgear"}, "192.0.2.30": {"vendor": "Synology"},
                      "192.0.2.2": {"vendor": "Cisco"}, "192.0.2.40": {"vendor": "TP-Link"}}}
    snapshot = {"nodes": [], "unread": [{"switch": "s:core", "port": "gi5", "mac": "aa:bb:cc:00:00:20",
                                         "sys_name": "office-sw", "caps": ["bridge"], "ip": "", "device_id": None}]}
    found = suggestions(settings, ports, snapshot, DEVICES)
    assert [entry["ip"] for entry in found] == ["192.0.2.20"]          # NAS, configured and dismissed are left out
    assert found[0]["why"] == ["answers SNMPv3 (Netgear)", "announces itself as a bridge on core port gi5"]
    assert found[0]["device_id"] == 1 and found[0]["suggested_name"] == "office-switch"


def test_dont_ask_is_remembered(isolated_cwd, monkeypatch):
    from lanxang.config import local
    from lanxang.config.loader import load_config

    monkeypatch.setattr(local, "_APPLIED", set())
    assert handle_post("/api/settings/switches/dismiss", {"ip": "192.0.2.20"})[0] == 200
    assert handle_post("/api/settings/switches/dismiss", {"ip": "192.0.2.20"})[0] == 200
    assert handle_post("/api/settings/switches/dismiss", {"ip": "<script>"})[0] == 400
    assert load_config().wiring.not_managed == ["192.0.2.20"]
