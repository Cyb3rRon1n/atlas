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
                "status": node["status"],
                # Usage numbers from the same /nodes list (absent on offline nodes).
                **{key: node[key] for key in ("cpu", "maxcpu", "mem", "maxmem", "disk", "maxdisk", "uptime")
                   if key in node}
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
                "template": bool(resource.get("template")),
            }
        )


    return guests


def discover_node_storage(client, node_name):
    """
    One node's storage usage and ZFS pool health, for the home page's storage
    card. Each lookup degrades to [] on its own (e.g. a token without
    Sys.Audit can still list nodes and guests).
    """

    result = {"storage": [], "zfs": []}

    try:
        result["storage"] = [
            {key: item.get(key) for key in ("storage", "type", "used", "total", "active")}
            for item in client.nodes(node_name).storage.get()
        ]
    except Exception:
        pass

    try:
        result["zfs"] = [
            {key: pool.get(key) for key in ("name", "health", "size", "alloc")}
            for pool in client.nodes(node_name).disks.zfs.get()
        ]
    except Exception:
        pass

    return result
