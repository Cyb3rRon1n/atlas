def diff_virtualization(previous, current):
    """
    previous/current are each {"nodes": [...], "guests": [...]} or falsy.

    Returns a list of change dicts. previous being falsy (no prior scan,
    or a saved environment that was never Proxmox-scanned) means there
    is no baseline to diff against, so nothing is reported - showing
    every node/guest as synthetic "added" noise on a first scan isn't
    useful when the scan output already lists them all.
    """

    if not previous:
        return []


    changes = []

    previous_nodes = {
        node["name"]: node
        for node in previous.get("nodes", [])
    }

    current_nodes = {
        node["name"]: node
        for node in current.get("nodes", [])
    }

    for name, node in current_nodes.items():

        if name not in previous_nodes:

            changes.append({
                "type": "node_added",
                "node": name
            })

        elif previous_nodes[name]["status"] != node["status"]:

            changes.append({
                "type": "node_status_changed",
                "node": name,
                "from": previous_nodes[name]["status"],
                "to": node["status"]
            })

    for name in previous_nodes:

        if name not in current_nodes:

            changes.append({
                "type": "node_removed",
                "node": name
            })


    previous_guests = {
        guest["vmid"]: guest
        for guest in previous.get("guests", [])
    }

    current_guests = {
        guest["vmid"]: guest
        for guest in current.get("guests", [])
    }

    for vmid, guest in current_guests.items():

        if vmid not in previous_guests:

            changes.append({
                "type": "guest_added",
                "vmid": vmid,
                "name": guest["name"],
                "guest_type": guest["type"]
            })

        elif previous_guests[vmid]["status"] != guest["status"]:

            changes.append({
                "type": "guest_status_changed",
                "vmid": vmid,
                "name": guest["name"],
                "from": previous_guests[vmid]["status"],
                "to": guest["status"]
            })

    for vmid, guest in previous_guests.items():

        if vmid not in current_guests:

            changes.append({
                "type": "guest_removed",
                "vmid": vmid,
                "name": guest["name"]
            })

    return changes


def format_change(change) -> str:

    change_type = change["type"]

    if change_type == "node_added":
        return f"+ Node '{change['node']}' added"

    if change_type == "node_removed":
        return f"- Node '{change['node']}' removed"

    if change_type == "node_status_changed":
        return (
            f"~ Node '{change['node']}' status changed: "
            f"{change['from']} → {change['to']}"
        )

    if change_type == "guest_added":
        return (
            f"+ Guest '{change['name']}' ({change['vmid']}, "
            f"{change['guest_type']}) added"
        )

    if change_type == "guest_removed":
        return f"- Guest '{change['name']}' ({change['vmid']}) removed"

    if change_type == "guest_status_changed":
        return (
            f"~ Guest '{change['name']}' ({change['vmid']}) status changed: "
            f"{change['from']} → {change['to']}"
        )

    return f"? Unknown change: {change}"
