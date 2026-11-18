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