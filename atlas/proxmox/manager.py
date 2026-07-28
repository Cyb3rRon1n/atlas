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
