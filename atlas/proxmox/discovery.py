import re


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

    result = {"storage": [], "zfs": [], "disks": []}

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

    try:
        disks = client.nodes(node_name).disks.list.get()
    except Exception:
        disks = []
    for disk in disks:
        row = {"dev": disk.get("devpath"), "type": disk.get("type") or "", "size": disk.get("size"),
               "model": (disk.get("model") or "").replace("_", " "), "serial": disk.get("serial") or "",
               "health": (disk.get("health") or "").upper(), "used": disk.get("used") or "",
               "life": disk.get("wearout") if isinstance(disk.get("wearout"), int) else None}
        try:
            row.update(smart_numbers(client.nodes(node_name).disks.smart.get(disk=row["dev"])))
        except Exception:
            pass                                  # health and wear from the list are still worth showing
        result["disks"].append(row)

    return result


# SMART attribute ids: temperature, and the counters that only go up as a disk goes bad.
TEMPERATURE_IDS = ("194", "190")
BAD_SECTOR_IDS = ("5", "197", "198")       # reallocated, pending, offline uncorrectable


def _first_int(value):

    match = re.match(r"\s*(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def smart_numbers(smart):
    """{"temp": C or None, "bad": sectors or None} from Proxmox's /disks/smart answer (ATA attributes, or the
    smartctl text an NVMe drive gives)."""

    attributes = {str(a.get("id", "")).strip(): a.get("raw") for a in smart.get("attributes") or []}
    temp = next((_first_int(attributes[i]) for i in TEMPERATURE_IDS if i in attributes), None)
    counts = [_first_int(attributes[i]) for i in BAD_SECTOR_IDS if i in attributes]
    bad = sum(c for c in counts if c is not None) if counts else None
    text = smart.get("text") or ""
    if temp is None:
        match = re.search(r"^Temperature:\s+(\d+) Celsius", text, re.M)
        temp = int(match.group(1)) if match else None
    if bad is None:
        match = re.search(r"^Media and Data Integrity Errors:\s+([\d,]+)", text, re.M)
        bad = int(match.group(1).replace(",", "")) if match else None
    return {"temp": temp, "bad": bad}
