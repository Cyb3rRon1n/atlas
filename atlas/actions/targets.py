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


def known_libvirt_guest_names(environment: dict) -> set[str]:
    """
    Flatten every libvirt/KVM guest name Atlas actually observed via
    LibvirtPlugin - matches by name, not known_guest_ids()'s vmid,
    since virsh operates on domain names. environment["virtualization"]
    is plugin-keyed here (e.g. {"Libvirt": {"guests": [...]}}), not
    atlas proxmox scan's flat {"nodes": [...], "guests": [...]} -
    isinstance() skips that shape rather than crashing on it, same
    defensive check atlas.web.render uses for the same ambiguity.
    """

    names = set()

    for plugin_data in environment.get("virtualization", {}).values():

        if not isinstance(plugin_data, dict):
            continue

        for guest in plugin_data.get("guests", []):

            if "name" in guest:
                names.add(guest["name"])

    return names
