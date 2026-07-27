def discover_nodes(client):

    if not client:
        return []


    nodes = []

    result = (
        client.nodes.get()
    )


    for node in result:

        nodes.append(
            {
                "name": node["node"],
                "status": node["status"]
            }
        )


    return nodes


def discover_resources(client):
    """
    Discover every VM and container across the cluster in one call.

    Uses /cluster/resources (type=vm), which covers both qemu (VMs)
    and lxc (containers) - distinguished by the "type" field on each
    entry - rather than enumerating nodes and querying each one.
    """

    if not client:
        return []


    guests = []

    result = (
        client.cluster.resources.get(
            type="vm"
        )
    )


    for resource in result:

        guests.append(
            {
                "vmid": resource["vmid"],
                "name": resource.get("name", ""),
                "node": resource.get("node", ""),
                "type": resource.get("type", ""),
                "status": resource.get("status", ""),
                "cpu": resource.get("cpu"),
                "maxcpu": resource.get("maxcpu"),
                "mem": resource.get("mem"),
                "maxmem": resource.get("maxmem"),
                "disk": resource.get("disk"),
                "maxdisk": resource.get("maxdisk"),
                "uptime": resource.get("uptime"),
            }
        )


    return guests
