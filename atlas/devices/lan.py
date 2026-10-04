"""
Whole-LAN discovery without ping or raw sockets: a TCP connect to every
address makes the kernel ARP-resolve it, so every live device's MAC lands
in /proc/net/arp whether or not the port is open. Needs only host
networking (network_mode: host), no NET_RAW, no new dependency.
"""

import ipaddress
import socket
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from atlas.devices import Sighting


MAX_HOSTS = 1024

# Slow devices (Wi-Fi IoT, phones in power-save) can take 1-3 seconds to
# respond to ARP resolution; the kernel retries about once per second.
# Wait before reading /proc/net/arp to catch late replies.
ARP_SETTLE_SECONDS = 2.0

POKE_PORT = 9


def _read(path):

    return Path(path).read_text()


def _hex_ip(value):

    # /proc/net/route stores addresses as little-endian hex.
    return socket.inet_ntoa(struct.pack("<L", int(value, 16)))


def _route_rows(text):

    return [line.split() for line in text.splitlines()[1:] if len(line.split()) >= 8]


def default_interface(text):

    return next((row[0] for row in _route_rows(text) if row[1] == "00000000"), None)


def parse_route(text):
    """Networks directly attached to the default-route interface - the LAN.

    Only routes with no gateway are directly attached; a routed static
    network (via a gateway) isn't the local LAN. Link-local networks
    (169.254.0.0/16) are never a LAN to scan either. Host routes (/32)
    contained in a broader network are dropped.
    """

    interface = default_interface(text)

    if interface is None:
        return []

    networks = set()

    for row in _route_rows(text):

        if row[0] != interface or row[1] == "00000000" or row[2] != "00000000":
            continue

        network = ipaddress.IPv4Network(f"{_hex_ip(row[1])}/{_hex_ip(row[7])}")

        if not network.is_link_local:
            networks.add(network)

    # Drop host routes (/32) that are contained in another network.
    result = []
    for network in sorted(networks, key=lambda n: (n.prefixlen, str(n))):
        if not any(network.subnet_of(other) and network != other for other in networks):
            result.append(str(network))

    return result


def default_gateway(route_text):
    """The dotted IPv4 gateway of the default route (destination 00000000),
    or None if there's no default route at all."""

    row = next((row for row in _route_rows(route_text) if row[1] == "00000000"), None)

    return _hex_ip(row[2]) if row else None


def parse_arp(text):
    """Complete neighbour entries only (flag 0x2); incomplete means nobody answered."""

    table = {}

    for line in text.splitlines()[1:]:

        parts = line.split()

        if len(parts) >= 6 and int(parts[2], 16) & 0x2 and parts[3] != "00:00:00:00:00:00":
            table[parts[0]] = parts[3].lower()

    return table


def _poke(ip, timeout):

    try:
        with socket.socket() as sock:
            sock.settimeout(timeout)
            sock.connect_ex((ip, POKE_PORT))

    except OSError:
        pass


def sweep(subnets, timeout=0.5):

    hosts = [str(host) for subnet in subnets for host in ipaddress.IPv4Network(subnet, strict=False).hosts()]

    if len(hosts) > MAX_HOSTS:
        raise ValueError(f"{len(hosts)} addresses - atlas scans at most {MAX_HOSTS}; narrow scan.subnets")

    with ThreadPoolExecutor(max_workers=64) as pool:
        list(pool.map(lambda ip: _poke(ip, timeout), hosts))


def _reverse_dns(ip):

    try:
        return socket.gethostbyaddr(ip)[0]

    except OSError:
        return None


def local_sighting(interface):
    """This host never appears in its own ARP table - add it explicitly."""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", POKE_PORT))  # no packet is sent for UDP connect
            ip = sock.getsockname()[0]

        mac = _read(f"/sys/class/net/{interface}/address").strip().lower()

    except OSError:
        return None

    return Sighting("lan", mac, ip=ip, mac=mac, hostname=socket.gethostname(), detail={"self": True})


def scan(subnets=None, timeout=0.5):

    route = _read("/proc/net/route")
    subnets = list(subnets or parse_route(route))

    if not subnets:
        raise RuntimeError("no subnet to scan - set scan.subnets in atlas.yaml")

    sweep(subnets, timeout)

    time.sleep(ARP_SETTLE_SECONDS)

    networks = [ipaddress.IPv4Network(subnet, strict=False) for subnet in subnets]
    arp = {
        ip: mac for ip, mac in parse_arp(_read("/proc/net/arp")).items()
        if any(ipaddress.IPv4Address(ip) in network for network in networks)
    }

    with ThreadPoolExecutor(max_workers=16) as pool:
        names = dict(zip(arp, pool.map(_reverse_dns, arp)))

    sightings = [Sighting("lan", mac, ip=ip, mac=mac, hostname=names[ip]) for ip, mac in arp.items()]

    gateway = default_gateway(route)

    for sighting in sightings:
        if sighting.ip == gateway:
            sighting.detail["gateway"] = True

    interface = default_interface(route)
    me = local_sighting(interface) if interface else None

    if me and me.mac not in {sighting.mac for sighting in sightings}:
        sightings.append(me)

    return subnets, sightings
