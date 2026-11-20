"""
Port-level wired topology (lanxang wiring scan -> web /cabling). Shared helpers
live here; each source has its own module so a vendor adapter (UniFi) stays
optional and the vendor-neutral path (SNMP standard MIBs) stands alone.
"""

import re


class WiringError(Exception):
    """A source failed in a way the operator can act on (message is safe to show: no secrets)."""


VIRTUAL_OUIS = ("bc:24:11", "52:54:00", "00:16:3e")


def env_key(name):

    return re.sub(r"[^A-Za-z0-9]", "_", name).upper()


def normalize_mac(value):

    if not value:
        return None

    text = re.sub(r"^Hex-STRING:\s*", "", str(value).strip())
    digits = re.sub(r"[\s:.\-]", "", text)

    if not re.fullmatch(r"[0-9A-Fa-f]{12}", digits):
        return None

    return ":".join(digits[i:i + 2] for i in range(0, 12, 2)).lower()


def is_virtual_mac(mac):

    return bool(int(mac[:2], 16) & 0x02) or mac[:8] in VIRTUAL_OUIS


def wiring_node(device, snapshot):
    """The wired-map node (latest wiring scan) that is this device - matched by IP or a sighting's MAC - or None."""

    macs = {normalize_mac(s.get("mac")) for s in device["sightings"]} - {None}
    ips = {device["ip"]} | {s.get("ip") for s in device["sightings"]}
    for node in (snapshot or {}).get("nodes") or []:
        if node.get("kind") != "unknown" and ((node.get("ip") and node["ip"] in ips)
                                              or normalize_mac(node.get("mac")) in macs):
            return node
    # A gateway's LAN MAC often differs from the base MAC its controller reports: match the LAN scan's default gateway.
    gateways = [n for n in (snapshot or {}).get("nodes") or [] if n.get("kind") == "gateway"]
    if len(gateways) == 1 and any(s.get("source") == "lan" and (s.get("detail") or {}).get("gateway") is True
                                  for s in device["sightings"]):
        return gateways[0]

    return None
