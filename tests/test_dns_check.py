import socket
import struct
import threading
from datetime import datetime, timedelta

from atlas.config.models import AtlasConfig, InternetConfig
from atlas.monitoring import internet
from atlas.monitoring.uptime import UptimeStore

REAL_ASK = internet._ask          # conftest swaps the module's copy for a stub; this is the real one


def _fake_server(rcode):
    """A one-shot UDP DNS server on 127.0.0.1 answering with rcode; returns (port, thread)."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(3)

    def serve():
        data, peer = sock.recvfrom(512)
        assert data[12:] .startswith(b"\x07example\x03com\x00") and data[-4:] == b"\x00\x01\x00\x01"
        sock.sendto(data[:2] + struct.pack(">BB", 0x81, 0x80 | rcode) + data[4:], peer)
        sock.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return sock.getsockname()[1], thread


def test_a_real_query_over_udp():
    for rcode, answered in ((0, True), (3, True), (2, False)):        # NOERROR, NXDOMAIN fine; SERVFAIL not
        port, thread = _fake_server(rcode)
        assert (REAL_ASK("127.0.0.1", "example.com", 2, port=port) is not None) is answered
        thread.join()
    closed = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    assert REAL_ASK("127.0.0.1", "example.com", 0.3, port=port) is None   # nobody listening


def test_one_row_per_server_or_the_system_resolver():
    config = InternetConfig(dns_servers=["192.0.2.53", "192.0.2.1"])
    results = internet.check_dns(config, ask=lambda server, name, timeout: None if server == "192.0.2.1" else 4.0)
    assert results == {"DNS 192.0.2.53": (True, 4.0, "found example.com"),
                       "DNS 192.0.2.1": (False, None, "couldn't look up example.com")}
    assert list(internet.check_dns(InternetConfig(), system=lambda name, timeout: 9.0)) == ["DNS"]
    assert internet.all_names(InternetConfig(dns_name="")) == ["Internet", "Router"]


def test_dns_alerts_only_while_the_internet_is_up(temp_db):
    store, sent = UptimeStore(temp_db), []
    settings = AtlasConfig()
    t = datetime(2026, 11, 17, 12)
    up, dead = (lambda *a: (True, 10.0, "3 of 3 answered")), (lambda *a: (False, None, "no answer"))
    dns_ok = lambda config: {"DNS": (True, 5.0, "found example.com")}
    dns_bad = lambda config: {"DNS": (False, None, "couldn't look up example.com")}
    steps = [(up, dns_ok), (up, dns_bad), (up, dns_bad), (up, dns_bad), (up, dns_ok),
             (dead, dns_bad), (dead, dns_bad), (dead, dns_bad)]
    for i, (net, dns) in enumerate(steps):
        internet.run(settings, store, t + timedelta(minutes=i), internet=net, router=lambda gw: None, dns=dns,
                     send=sent.append)
    keys = [text.key for text in sent]
    assert keys == ["internet:dns:DNS", "internet:dns:DNS", "internet:down"]             # failing, works again, down
    assert "Name lookups are failing" in sent[0] and "work again" in sent[1]
