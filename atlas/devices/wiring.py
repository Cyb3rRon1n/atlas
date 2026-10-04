"""
Whether a device is wired or wireless, when the operator hasn't said so.
An operator-set value always wins - this never overwrites it, only fills
the gap with a best-effort guess from evidence already collected (no new
scan). A proxmox-sighted device (a VM/LXC) never gets guessed wireless: its
MAC is virtual and can carry the locally administered bit for reasons that
have nothing to do with radios, so a proxmox sighting rules the guess out
entirely rather than letting that bit mislead it. Otherwise, the guess
looks for a kind that's typically radio-only (phone, iot), "wlan" in the
device's own name or any sighting's hostname, or a locally administered
MAC (the kind randomized/virtual interfaces use - Wi-Fi radios, phones -
set the second-lowest bit of the first octet). Known virtual-NIC prefixes
(`52:54:00` - QEMU/libvirt, `02:42` - Docker) also set that bit for reasons
that have nothing to do with radios either, so they're excluded from the
locally-administered check the same way a proxmox sighting is - matched
case-insensitively, since a MAC's hex letters can come back either case.
"""

WIRELESS_KINDS = {"phone", "iot"}

VIRTUAL_NIC_PREFIXES = ("52:54:00", "02:42")


def _locally_administered(mac):

    try:
        if (mac or "").lower().startswith(VIRTUAL_NIC_PREFIXES):
            return False

        return bool(int(mac[:2], 16) & 0x02)

    except (TypeError, ValueError):
        # Missing or malformed MAC - no evidence either way, not an error.
        return False


def _has_wlan(text):

    return "wlan" in (text or "").lower()


def effective_connection(device):
    """
    (connection, guessed) for one atlas.devices.store.InventoryStore.devices()
    entry. `guessed` is only True when the stored value was "unknown" and a
    wireless signal was found - the raw stored value stays "unknown" either
    way, so it's still recoverable later if the guess turns out wrong.
    """

    if device["connection"] != "unknown":
        return device["connection"], False

    sightings = device["sightings"]

    if any(sighting.get("source") == "proxmox" for sighting in sightings):
        return "unknown", False

    if (device["kind"] in WIRELESS_KINDS
            or _has_wlan(device.get("name"))
            or any(_has_wlan(sighting.get("hostname")) for sighting in sightings)
            or any(_locally_administered(sighting.get("mac")) for sighting in sightings)):
        return "wireless", True

    return "unknown", False
