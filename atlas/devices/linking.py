"""
Which device a newly seen sighting belongs to. Links only on evidence that
can't be a coincidence (same MAC; a configured host's address; a Proxmox
guest's IP matching a LAN sighting). A name match is only a suggestion -
a wrong automatic merge is worse than a visible duplicate.
"""

import ipaddress


def short_name(name):
    """An IP-named device (no reverse DNS) isn't a dotted hostname - splitting
    it on "." would turn e.g. "192.168.10.57" into the meaningless "192"."""

    name = (name or "").strip().lower()

    try:
        ipaddress.ip_address(name)
        return name
    except ValueError:
        return name.split(".")[0]


def match(new, known):

    if new.mac:
        for entry in known:
            if entry["mac"] == new.mac and entry["source"] != new.source:
                return "link", entry["device_id"]

    if new.ip:
        for entry in known:
            # ponytail: stale IPs are offered from any past sighting, not just the
            # source's latest ok run; safe in PR 1 (proxmox sightings carry no IP
            # yet, manual IPs are operator claims) - restrict to sightings seen in
            # the source's latest ok run once guest IPs are added.
            if entry["ip"] == new.ip and (entry["source"] == "manual" or {entry["source"], new.source} == {"lan", "proxmox"}):
                return "link", entry["device_id"]

    name = short_name(new.hostname)

    if name:
        for entry in known:
            if name in (short_name(entry["device_name"]), short_name(entry["hostname"])):
                return "suggest", entry["device_id"]

    return "new", None
