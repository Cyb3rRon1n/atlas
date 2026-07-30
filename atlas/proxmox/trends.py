def _guest_metric_value(guest, metric_name):

    if metric_name == "cpu_percent":

        cpu = guest.get("cpu")
        return cpu * 100 if cpu is not None else None

    if metric_name == "memory_percent":

        mem = guest.get("mem")
        maxmem = guest.get("maxmem")
        return (mem / maxmem) * 100 if mem is not None and maxmem else None

    return None


def guest_metric_trend(records, vmid, metric_name):
    """
    records is KnowledgeQueries.environment_history()'s most-recent-
    first result - same input host_metric_trend()/container_metric_
    trend() take. Guest data lives under "virtualization" (populated
    by atlas proxmox scan), a completely separate save schedule from
    "monitoring" (atlas monitor) - skips any row without virtualization
    data at all, same "not every row is a full snapshot" rule the
    monitoring trend functions already follow for exactly this reason.
    Matches guests by vmid (str), not name - the same stable-identifier
    principle diff_virtualization() already uses, since a rename would
    otherwise look like a different guest disappearing and a new one
    appearing.
    """

    points = []

    for record in records:

        guests = record["data"].get("virtualization", {}).get("guests", [])
        guest = next(
            (g for g in guests if str(g.get("vmid")) == str(vmid)), None
        )

        if guest is None:
            continue

        value = _guest_metric_value(guest, metric_name)

        if value is not None:
            points.append((record["created_at"], value))

    return list(reversed(points))


def known_guests(records):
    """
    {vmid: name} for every guest that appears in any snapshot's
    virtualization data, so the CLI can list per-guest trends (and
    print a real name, not just a vmid) without a separate lookup.
    """

    guests = {}

    for record in records:

        for guest in record["data"].get("virtualization", {}).get("guests", []):

            vmid = guest.get("vmid")

            if vmid is not None:
                guests[str(vmid)] = guest.get("name", "")

    return dict(sorted(guests.items(), key=lambda item: int(item[0])))
