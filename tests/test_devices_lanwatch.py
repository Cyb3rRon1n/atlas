import socket
import struct
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from lanxang.config.models import AtlasConfig
from lanxang.devices import lanwatch
from lanxang.devices.lanwatch import alerts, assess, build_discover, parse_offer, probe_dhcp, run
from lanxang.posture.model import build_posture
from lanxang.posture.store import PostureStore


GW, GW_MAC, EVIL = "192.0.2.1", "aa:aa:aa:00:00:01", "bb:bb:bb:00:00:02"
NOW = datetime(2026, 11, 15, 12, 0)


def offer(xid, server="192.0.2.1", offered="192.0.2.50", router="192.0.2.1", kind=2):
    header = bytearray(240)
    header[0] = 2
    header[4:8] = struct.pack("!I", xid)
    header[16:20] = socket.inet_aton(offered)
    header[236:240] = lanwatch.MAGIC
    opts = bytes([53, 1, kind, 54, 4]) + socket.inet_aton(server) + bytes([3, 4]) + socket.inet_aton(router) + b"\xff"
    return bytes(header) + opts


def test_discover_packet_shape():
    packet = build_discover(0x12345678)
    assert packet[0] == 1 and struct.unpack("!I", packet[4:8])[0] == 0x12345678
    assert struct.unpack("!H", packet[10:12])[0] == 0x8000             # broadcast flag: answer by broadcast
    assert packet[28:34] == lanwatch.PROBE_MAC and packet[28] & 0x02   # locally administered MAC
    assert packet[236:240] == lanwatch.MAGIC and packet[240:243] == bytes([53, 1, 1])


def test_parse_offer_matches_xid_and_type():
    assert parse_offer(offer(7), 7) == {"server": GW, "offered": "192.0.2.50", "router": GW}
    assert parse_offer(offer(7), 8) is None                    # someone else's exchange
    assert parse_offer(offer(7, kind=5), 7) is None            # an ACK, not an offer
    assert parse_offer(b"junk", 7) is None


class FakeSocket:
    def __init__(self, servers):
        self.servers, self.replies, self.timeouts = servers, [], []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def sendto(self, data, address):
        assert address == ("255.255.255.255", 67)
        xid = struct.unpack("!I", data[4:8])[0]
        self.replies = [(offer(xid, server=s), (s, 67)) for s in self.servers] + [(offer(xid), (GW, 67))]

    def settimeout(self, value):
        self.timeouts.append(value)

    def recvfrom(self, size):
        if not self.replies:
            raise socket.timeout()
        return self.replies.pop(0)


def test_probe_collects_every_server_once():
    offers = probe_dhcp(1.0, sock=FakeSocket([GW, "192.0.2.66"]))
    assert [o["server"] for o in offers] == [GW, "192.0.2.66"]


def check(offers=(), arp=None, clients=(), allowed=(), state=None, error=""):
    return assess(offers=None if offers is None else [{"server": s, "offered": "192.0.2.50", "router": s}
                                                      for s in offers],
                  probe_error=error, gateway_ip=GW, arp={GW: GW_MAC} if arp is None else arp,
                  clients=list(clients), allowed=list(allowed), state=state or {})


def kinds(issues):
    return {(i["kind"], i["level"]) for i in issues}


def test_only_the_gateway_answering_is_quiet_and_learns_its_mac():
    issues, state = check([GW])
    assert issues == [] and state == {"gateway_mac": GW_MAC, "silent": 0, "heard": True}


def test_unknown_dhcp_server_is_a_problem_unless_allowed():
    issues, _ = check([GW, "192.0.2.66"], arp={GW: GW_MAC, "192.0.2.66": EVIL})
    assert kinds(issues) == {("rogue_dhcp", "bad")} and EVIL in issues[0]["detail"]
    assert check([GW, "192.0.2.66"], allowed=["192.0.2.66"])[0] == []


def test_silence_alerts_only_after_repeated_runs_and_probe_errors_never_count():
    issues, state = check([], state={"heard": True})
    assert issues == [] and state["silent"] == 1
    assert kinds(check([], state=state)[0]) == {("dhcp_down", "bad")}
    # never heard any server: a host firewall dropping UDP 68 is far likelier - watch only
    assert kinds(check([], state={"silent": 5})[0]) == {("dhcp_unheard", "watch")}
    issues, state = check([], error="permission denied", state={"silent": 1})
    assert issues == [] and state["silent"] == 1
    assert check(None)[1].get("silent") is None                 # probe turned off


def test_gateway_mac_change_is_a_problem_and_names_the_impostor():
    learned = {"gateway_mac": GW_MAC}
    issues, state = check([GW], arp={GW: EVIL, "192.0.2.77": EVIL}, state=learned)
    assert kinds(issues) == {("gateway_mac", "bad")} and "192.0.2.77" in issues[0]["detail"]
    assert state["gateway_mac"] == GW_MAC                       # never silently re-learned


def test_shared_gateway_mac_and_duplicate_ip_are_watch_only():
    assert kinds(check([GW], arp={GW: GW_MAC, "192.0.2.9": GW_MAC})[0]) == {("shared_mac", "watch")}
    clients = [{"mac": "cc:00:00:00:00:01", "ip": "192.0.2.20", "name": "nas"},
               {"mac": "cc:00:00:00:00:02", "ip": "192.0.2.20", "name": ""}]
    assert kinds(check([GW], clients=clients)[0]) == {("duplicate_ip", "watch")}


def test_unifi_client_using_the_gateway_address_is_a_problem():
    clients = [{"mac": EVIL, "ip": GW, "name": "laptop"}]
    assert kinds(check([GW], clients=clients, state={"gateway_mac": GW_MAC})[0]) == {("gateway_claim", "bad")}


def test_alerts_once_and_on_recovery():
    bad, _ = check([GW, "192.0.2.66"])
    assert len(alerts([], bad)) == 1 and "Unknown DHCP server" in alerts([], bad)[0]
    assert alerts(bad, bad) == []
    assert "Resolved" in alerts(bad, [])[0]


def files(arp):
    route = ("Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
             f"eth0\t00000000\t{struct.unpack('<L', socket.inet_aton(GW))[0]:08X}\t0003\t0\t0\t0\t00000000\n")
    table = "IP address HW type Flags HW address Mask Device\n" + "".join(
        f"{ip} 0x1 0x2 {mac} * eth0\n" for ip, mac in arp.items())
    return lambda path: route if path.endswith("route") else table


def test_run_stores_status_alerts_and_trust(temp_db):
    store, sent, settings = PostureStore(temp_db), [], AtlasConfig()
    probe = lambda timeout: [{"server": GW, "offered": "192.0.2.50", "router": GW}]

    run(settings, store, NOW, probe=probe, read=files({GW: GW_MAC}), send=sent.append)
    assert sent == [] and store.statuses()["lan"]["detail"]["gateway_mac"] == GW_MAC

    run(settings, store, NOW, probe=probe, read=files({GW: EVIL}), send=sent.append)
    assert len(sent) == 1 and "Gateway MAC" in sent[0]
    run(settings, store, NOW, probe=probe, read=files({GW: EVIL}), send=sent.append)
    assert len(sent) == 1                                       # no repeat
    strip = {i["key"]: i for i in build_posture(store, NOW)["strip"]}
    assert (strip["lan"]["state"], strip["lan"]["value"]) == ("warn", "1 problem")

    detail = run(settings, store, NOW, probe=probe, read=files({GW: EVIL}), send=sent.append, trust_gateway=True)
    assert detail["issues"] == [] and detail["gateway_mac"] == EVIL and "Resolved" in sent[-1]
    strip = {i["key"]: i for i in build_posture(store, NOW)["strip"]}
    assert strip["lan"]["state"] == "ok" and GW in strip["lan"]["detail"]
    assert {i["key"]: i for i in build_posture(store, NOW + timedelta(hours=3))["strip"]}["lan"]["state"] == "unknown"


def test_probe_error_is_reported_not_alerted(temp_db):
    def probe(timeout):
        raise PermissionError("binding UDP port 68 needs root")
    detail = run(AtlasConfig(), PostureStore(temp_db), NOW, probe=probe, read=files({GW: GW_MAC}), send=pytest.fail)
    assert "port 68" in detail["probe_error"] and detail["issues"] == []


def test_helper_used_when_port_68_is_privileged(monkeypatch):
    def denied(timeout):
        raise PermissionError("denied")
    monkeypatch.setattr(lanwatch, "probe_dhcp", denied)
    monkeypatch.setattr(lanwatch.shutil, "which", lambda name: "/usr/local/bin/" + name)
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='[{"server": "192.0.2.1"}]', stderr="")
    assert lanwatch.probe_with_helper(1.0, run=fake_run) == [{"server": GW}]
    assert calls[0][:4] == ["/usr/local/bin/atlas-dhcp-python", "-I", "-m", "lanxang.devices.lanwatch"]
    monkeypatch.setattr(lanwatch.shutil, "which", lambda name: None)
    with pytest.raises(PermissionError, match="helper"):
        lanwatch.probe_with_helper(1.0, run=fake_run)
