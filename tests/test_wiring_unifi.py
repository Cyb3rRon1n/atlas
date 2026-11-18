import io
import json

import pytest

from lanxang.config.models import WiringUnifi
from lanxang.wiring import WiringError
from lanxang.wiring.unifi import fetch_unifi, parse_unifi

DEVICES = [
    {"mac": "02:00:00:00:00:01", "name": "gateway", "model": "UCGF", "type": "udm", "ip": "192.0.2.1",
     "port_table": [{"port_idx": 1, "name": "Port 1", "up": True, "speed": 1000, "mac": "02:00:00:00:00:02"},
                    {"port_idx": 4, "name": "Port 4", "up": True, "speed": 2500},
                    {"port_idx": 5, "name": "Port 5", "up": True, "speed": 2500}],
     "last_uplink": {"type": "wire", "uplink_mac": "00:00:5e:00:53:99", "port_idx": 5}},
    {"mac": "02:00:00:00:00:03", "name": "ap-express", "model": "UX7", "type": "udm", "ip": "192.0.2.3",
     "radio_table": [{"name": "wifi0"}],
     "port_table": [{"port_idx": 1, "up": True, "speed": 2500}, {"port_idx": 2, "up": True, "speed": 2500}],
     "last_uplink": {"type": "wire", "uplink_mac": "02:00:00:00:00:01", "uplink_remote_port": 4, "port_idx": 2}},
    {"mac": "02:00:00:00:00:04", "name": "mesh-ap", "model": "U6M", "type": "uap",
     "last_uplink": {"type": "wireless", "uplink_mac": "02:00:00:00:00:03"}},
    {"mac": "02:00:00:00:00:05", "name": "flex", "model": "USWED35", "type": "usw",
     "port_table": [{"port_idx": 5, "up": True, "speed": 2500}],
     "last_uplink": {"type": "wire", "uplink_mac": "02:00:00:00:00:03", "uplink_remote_port": 1, "port_idx": 5}},
]
CLIENTS = [
    {"mac": "00:00:5e:00:53:01", "is_wired": True, "hostname": "nas", "ip": "192.0.2.10",
     "sw_mac": "02:00:00:00:00:01", "sw_port": 1},
    {"mac": "00:00:5e:00:53:02", "is_wired": False, "hostname": "phone", "ap_mac": "02:00:00:00:00:03"},
]


def test_parse_unifi_roles_ports_uplinks():
    result = parse_unifi(DEVICES, CLIENTS)
    by_name = {d["name"]: d for d in result["devices"]}
    assert by_name["gateway"]["role"] == "gateway" and by_name["ap-express"]["role"] == "ap"
    assert by_name["mesh-ap"]["role"] == "ap" and by_name["flex"]["role"] == "switch"
    port4 = dict(by_name["gateway"]["ports"]["Port 4"])
    assert port4.pop("counters")["duplex"] == "unknown"
    assert port4 == {"index": 4, "up": True, "speed": 2500}
    assert by_name["ap-express"]["ports"]["Port 2"]["speed"] == 2500        # name falls back to "Port N"
    assert by_name["gateway"]["port_macs"] == {"02:00:00:00:00:02": "Port 1"}
    assert by_name["flex"]["uplink"] == {"type": "wire", "mac": "02:00:00:00:00:03", "remote_port": 1, "local_port": 5}
    assert result["clients"] == [{"mac": "00:00:5e:00:53:01", "name": "nas", "ip": "192.0.2.10",
                                  "switch_mac": "02:00:00:00:00:01", "switch_port": 1}]


class FakeResponse(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(json.dumps(payload).encode()); self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FakeOpener:
    def __init__(self, login_status=200):
        self.calls, self.login_status = [], login_status
    def open(self, request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else request
        self.calls.append((url, getattr(request, "data", None)))
        if url.endswith("/api/auth/login"):
            if self.login_status != 200:
                import urllib.error
                raise urllib.error.HTTPError(url, self.login_status, "nope", {}, None)
            return FakeResponse({})
        return FakeResponse({"data": DEVICES if url.endswith("stat/device") else CLIENTS})


def test_fetch_unifi():
    opener = FakeOpener()
    config = WiringUnifi(enabled=True, url="https://192.0.2.1")
    result = fetch_unifi(config, {"ATLAS_UNIFI_USER": "atlas", "ATLAS_UNIFI_PASS": "pw-123456"}, 5,
                         opener_factory=lambda: opener)
    assert len(result["devices"]) == 4
    assert opener.calls[1][0] == "https://192.0.2.1/proxy/network/api/s/default/stat/device"


def test_fetch_unifi_errors():
    config = WiringUnifi(enabled=True, url="https://192.0.2.1")
    with pytest.raises(WiringError, match="ATLAS_UNIFI_USER"):
        fetch_unifi(config, {}, 5, opener_factory=FakeOpener)
    with pytest.raises(WiringError, match="login refused"):
        fetch_unifi(config, {"ATLAS_UNIFI_USER": "a", "ATLAS_UNIFI_PASS": "b"}, 5,
                    opener_factory=lambda: FakeOpener(401))

def test_public_ip_is_not_shown():
    devices = [dict(DEVICES[0], ip="9.9.9.9")]
    assert parse_unifi(devices, [])["devices"][0]["ip"] == ""
