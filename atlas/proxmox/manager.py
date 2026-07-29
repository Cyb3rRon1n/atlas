import docker

from atlas.proxmox.discovery import discover_resources


def get_guest_info(client, vmid):

    guests = discover_resources(client)

    for guest in guests:

        if guest["vmid"] == vmid:
            return {
                "found": True,
                **guest
            }

    return {
        "found": False,
        "error": f"No guest with vmid {vmid} found"
    }


def restart_guest(client, node, vmid, guest_type):

    try:

        if guest_type == "lxc":
            client.nodes(node).lxc(vmid).status.reboot.post()
        else:
            client.nodes(node).qemu(vmid).status.reboot.post()

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }

    return {
        "success": True
    }


def stop_guest(client, node, vmid, guest_type):
    """
    Requests a graceful ACPI shutdown, not a hard power-off - the
    closer analog to Docker's container.stop(). Unlike Docker, this
    has no automatic force-fallback: if the guest OS isn't running an
    ACPI listener (or is hung), the request can stall rather than
    guarantee termination.
    """

    try:

        if guest_type == "lxc":
            client.nodes(node).lxc(vmid).status.shutdown.post()
        else:
            client.nodes(node).qemu(vmid).status.shutdown.post()

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }

    return {
        "success": True
    }


def resize_guest(client, node, vmid, guest_type, cpus=None, memory=None):
    """
    cpus maps to Proxmox's cpulimit (a float cap on host-core usage,
    the analog to Docker's --cpus), not cores/sockets (CPU topology -
    a different concept entirely, and not a "limit" at all). memory
    reuses docker.utils.parse_bytes() to accept the same human string
    format ("512m", "1g") resize_container already does, converted to
    the MB integer Proxmox's config API expects.
    """

    config = {}

    if cpus is not None:
        config["cpulimit"] = cpus

    if memory is not None:
        config["memory"] = docker.utils.parse_bytes(memory) // (1024 * 1024)

    try:

        if guest_type == "lxc":
            client.nodes(node).lxc(vmid).config.put(**config)
        else:
            client.nodes(node).qemu(vmid).config.put(**config)

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }

    return {
        "success": True
    }
