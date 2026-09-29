"""
Whole-LAN discovery without ping or raw sockets: a TCP connect to every
address makes the kernel ARP-resolve it, so every live device's MAC lands
in /proc/net/arp whether or not the port is open. Needs only host
networking (network_mode: host), no NET_RAW, no new dependency.
"""

import ipaddress
import socket
import struct
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from atlas.devices import Sighting


MAX_HOSTS = 1024

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
    """Networks directly attached to the default-route interface - the LAN."""

    interface = default_interface(text)

    if interface is None:
        return []

    return sorted({
        str(ipaddress.IPv4Network(f"{_hex_ip(row[1])}/{_hex_ip(row[7])}"))
        for row in _route_rows(text)
        if row[0] == interface and row[1] != "00000000"
    })


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

    networks = [ipaddress.IPv4Network(subnet, strict=False) for subnet in subnets]
    arp = {
        ip: mac for ip, mac in parse_arp(_read("/proc/net/arp")).items()
        if any(ipaddress.IPv4Address(ip) in network for network in networks)
    }

    with ThreadPoolExecutor(max_workers=16) as pool:
        names = dict(zip(arp, pool.map(_reverse_dns, arp)))

    sightings = [Sighting("lan", mac, ip=ip, mac=mac, hostname=names[ip]) for ip, mac in arp.items()]

    interface = default_interface(route)
    me = local_sighting(interface) if interface else None

    if me and me.mac not in {sighting.mac for sighting in sightings}:
        sightings.append(me)

    return subnets, sightings
