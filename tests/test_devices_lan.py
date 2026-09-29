import time

import pytest

import atlas.devices.lan as lan
from atlas.devices import Sighting


ROUTE = """Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT
eno1\t00000000\t010AA8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0
eno1\t000AA8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0
eno1\t010AA8C0\t00000000\t0001\t0\t0\t100\tFFFFFFFF\t0\t0\t0
eno1\t0000FEA9\t00000000\t0001\t0\t0\t100\t0000FFFF\t0\t0\t0
eno1\t0000000A\t010AA8C0\t0003\t0\t0\t100\t000000FF\t0\t0\t0
docker0\t000011AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0
"""

ARP = """IP address       HW type     Flags       HW address            Mask     Device
192.168.10.1     0x1         0x2         aa:bb:cc:00:00:01     *        eno1
192.168.10.57    0x1         0x2         AA:BB:CC:00:00:57     *        eno1
192.168.10.99    0x1         0x0         00:00:00:00:00:00     *        eno1
172.17.0.2       0x1         0x2         02:42:ac:11:00:02     *        docker0
"""


def test_parse_route_returns_default_interface_networks_only():
    """Drops the default route itself, the link-local row, and the routed
    (via-gateway) static route - only the directly-attached LAN remains."""

    assert lan.default_interface(ROUTE) == "eno1"
    assert lan.parse_route(ROUTE) == ["192.168.10.0/24"]


def test_parse_route_without_default_route():

    assert lan.parse_route(ROUTE.splitlines()[0] + "\n") == []


def test_parse_arp_keeps_complete_entries_lowercased():

    assert lan.parse_arp(ARP) == {
        "192.168.10.1": "aa:bb:cc:00:00:01",
        "192.168.10.57": "aa:bb:cc:00:00:57",
        "172.17.0.2": "02:42:ac:11:00:02",
    }


def test_sweep_refuses_huge_ranges():

    with pytest.raises(ValueError):
        lan.sweep(["10.0.0.0/16"], timeout=0.01)


def test_scan_filters_to_subnet_and_adds_self(monkeypatch):

    files = {"/proc/net/route": ROUTE, "/proc/net/arp": ARP}
    monkeypatch.setattr(lan, "_read", lambda path: files[path])
    monkeypatch.setattr(lan, "sweep", lambda subnets, timeout: None)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(lan, "_reverse_dns", lambda ip: "router.lan" if ip.endswith(".1") else None)
    monkeypatch.setattr(lan, "local_sighting", lambda iface: Sighting(
        "lan", "aa:bb:cc:00:01:57", ip="192.168.10.157", mac="aa:bb:cc:00:01:57", hostname="cyberpac", detail={"self": True}))

    subnets, sightings = lan.scan()

    assert subnets == ["192.168.10.0/24"]
    by_ip = {s.ip: s for s in sightings}
    assert set(by_ip) == {"192.168.10.1", "192.168.10.57", "192.168.10.157"}
    assert by_ip["192.168.10.1"].hostname == "router.lan"
    assert by_ip["192.168.10.57"].external_id == "aa:bb:cc:00:00:57"
    assert all(s.source == "lan" for s in sightings)


def test_scan_with_no_subnet_raises(monkeypatch):

    monkeypatch.setattr(lan, "_read", lambda path: "Iface\n")

    with pytest.raises(RuntimeError):
        lan.scan()


def test_scan_sleeps_after_sweep_and_before_reading_arp(monkeypatch):
    """Verify that scan() sleeps ARP_SETTLE_SECONDS between sweep and /proc/net/arp read."""

    call_order = []

    def mock_read(path):
        call_order.append(("read", path))
        if path == "/proc/net/route":
            return ROUTE
        elif path == "/proc/net/arp":
            return ARP
        return ""

    def mock_sweep(subnets, timeout):
        call_order.append(("sweep",))

    def mock_sleep(seconds):
        call_order.append(("sleep", seconds))

    monkeypatch.setattr(lan, "_read", mock_read)
    monkeypatch.setattr(lan, "sweep", mock_sweep)
    monkeypatch.setattr(time, "sleep", mock_sleep)
    monkeypatch.setattr(lan, "_reverse_dns", lambda ip: None)
    monkeypatch.setattr(lan, "local_sighting", lambda iface: None)

    lan.scan()

    # Check the order: sweep, then sleep, then read /proc/net/arp
    sweep_idx = next(i for i, call in enumerate(call_order) if call[0] == "sweep")
    sleep_idx = next(i for i, call in enumerate(call_order) if call[0] == "sleep")
    arp_read_idx = next(
        i for i, call in enumerate(call_order)
        if call[0] == "read" and call[1] == "/proc/net/arp"
    )

    assert sweep_idx < sleep_idx < arp_read_idx, (
        f"Expected sweep < sleep < read(/proc/net/arp), "
        f"got indices sweep={sweep_idx}, sleep={sleep_idx}, read=/proc/net/arp={arp_read_idx}"
    )

    # Verify sleep was called with the correct duration
    sleep_call = call_order[sleep_idx]
    assert sleep_call == ("sleep", lan.ARP_SETTLE_SECONDS)
