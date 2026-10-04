"""
Whether a device is wired or wireless, when the operator hasn't said so.
An operator-set value always wins - this never overwrites it, only fills
the gap with a best-effort guess from evidence already collected (no new
scan). A locally administered MAC (the kind randomized/virtual interfaces
use - Wi-Fi radios, phones, VMs - set the second-lowest bit of the first
octet) is the one signal available without a switch to query.
"""


def _locally_administered(mac):

    try:
        return bool(int(mac[:2], 16) & 0x02)

    except (TypeError, ValueError):
        # Missing or malformed MAC - no evidence either way, not an error.
        return False


def effective_connection(device):
    """
    (connection, guessed) for one atlas.devices.store.InventoryStore.devices()
    entry. `guessed` is only True when the stored value was "unknown" and a
    wireless signal was found - the raw stored value stays "unknown" either
    way, so it's still recoverable later if the guess turns out wrong.
    """

    if device["connection"] != "unknown":
        return device["connection"], False

    if device["kind"] == "phone" or any(_locally_administered(s.get("mac")) for s in device["sightings"]):
        return "wireless", True

    return "unknown", False
