"""
Which device a newly seen sighting belongs to. Links only on evidence that
can't be a coincidence (same MAC; a configured host's address; a Proxmox
guest's IP matching a LAN sighting). A name match is only a suggestion -
a wrong automatic merge is worse than a visible duplicate.
"""


def short_name(name):

    return (name or "").split(".")[0].strip().lower()


def match(new, known):

    if new.mac:
        for entry in known:
            if entry["mac"] == new.mac and entry["source"] != new.source:
                return "link", entry["device_id"]

    if new.ip:
        for entry in known:
            if entry["ip"] == new.ip and (entry["source"] == "manual" or {entry["source"], new.source} == {"lan", "proxmox"}):
                return "link", entry["device_id"]

    name = short_name(new.hostname)

    if name:
        for entry in known:
            if name in (short_name(entry["device_name"]), short_name(entry["hostname"])):
                return "suggest", entry["device_id"]

    return "new", None
