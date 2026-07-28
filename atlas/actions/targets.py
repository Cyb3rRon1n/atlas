def known_container_names(environment: dict) -> set[str]:
    """
    Flatten every container name Atlas actually observed, across all
    discovery plugins, e.g. environment["containers"] ==
    {"Docker": {"available": True, "containers": [{"name": "plex", ...}]}}.
    """

    names = set()

    for plugin_data in environment.get("containers", {}).values():

        for container in plugin_data.get("containers", []):

            if "name" in container:
                names.add(container["name"])

    return names


def known_guest_ids(environment: dict) -> set[str]:
    """
    Flatten every Proxmox guest vmid Atlas actually observed, as
    strings (action targets are always strings) - matches by vmid,
    not name, same stable-identifier principle as
    atlas.proxmox.changes.diff_virtualization.
    """

    guests = environment.get("virtualization", {}).get("guests", [])

    return {
        str(guest["vmid"])
        for guest in guests
        if "vmid" in guest
    }
