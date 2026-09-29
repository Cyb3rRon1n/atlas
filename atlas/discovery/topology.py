import re
import time
from concurrent.futures import ThreadPoolExecutor

from atlas.discovery.reachability import check_host


HOST_RULE = re.compile(r"Host\(`([^`]+)`\)")


def _docker_topology(client):
    """
    Containers grouped by the Docker network they sit on, with health and
    the public hostnames Traefik routes to them. A container sharing another
    one's network stack (network_mode container:gluetun) is listed under
    "via <that container>" - it has no network of its own.
    """

    if client is None:
        return {"available": False, "networks": {}}

    by_id = {}
    containers = client.containers.list(all=True)

    for container in containers:
        by_id[container.id] = container.name

    networks = {}

    for container in containers:

        attrs = container.attrs
        labels = attrs.get("Config", {}).get("Labels") or {}
        state = attrs.get("State", {})
        mode = attrs.get("HostConfig", {}).get("NetworkMode", "")

        entry = {
            "name": container.name,
            "status": state.get("Status", container.status),
            "health": (state.get("Health") or {}).get("Status", ""),
            "public": sorted({
                host
                for key, rule in labels.items()
                if key.startswith("traefik.http.routers.") and key.endswith(".rule")
                for host in HOST_RULE.findall(rule)
            })
        }

        if mode.startswith("container:"):
            target = mode.split(":", 1)[1]
            groups = [f"via {by_id.get(target, target[:12])}"]
        else:
            groups = sorted((attrs.get("NetworkSettings", {}).get("Networks") or {}).keys()) or [mode or "none"]

        # A container on several networks is drawn once, on its first (sorted) network.
        networks.setdefault(groups[0], []).append(entry)

    for members in networks.values():
        members.sort(key=lambda entry: entry["name"])

    return {"available": True, "networks": dict(sorted(networks.items(), key=lambda item: -len(item[1])))}


def collect_topology(config, docker_client=None, proxmox_resources=None):
    """
    Everything atlas can see - and what it's allowed to act on - in one
    snapshot for the network map: this host's containers by network,
    Proxmox guests, the configured LAN hosts (TCP reachability), and the AI
    endpoint. Callers pass the live clients; nothing here writes anywhere.
    """

    hosts = list(config.map.hosts)

    with ThreadPoolExecutor(max_workers=8) as pool:
        checks = list(pool.map(lambda host: check_host(host.address, host.ports, timeout=1.5), hosts))

    lan = [
        {
            "name": host.name,
            "address": host.address,
            "role": host.role,
            "reachable": check.get("reachable", False),
            "open_ports": [port["port"] for port in check.get("ports", []) if port["open"]]
        }
        for host, check in zip(hosts, checks)
    ]

    brain = None

    if config.intelligence.provider == "ollama":
        match = re.match(r"https?://([^:/]+):?(\d+)?", config.intelligence.ollama_host)
        if match:
            check = check_host(match.group(1), [int(match.group(2) or 11434)], timeout=1.5)
            brain = {"provider": "ollama", "model": config.intelligence.model,
                     "address": match.group(1), "reachable": check.get("reachable", False)}
    else:
        brain = {"provider": config.intelligence.provider, "model": config.intelligence.model,
                 "address": "cloud API", "reachable": None}

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "host": config.name,
        "docker": _docker_topology(docker_client),
        "proxmox": {
            "enabled": config.proxmox.enabled,
            "host": config.proxmox.host,
            "guests": [
                {key: guest.get(key) for key in ("vmid", "name", "type", "status", "template")}
                for guest in (proxmox_resources or [])
            ]
        },
        "lan": lan,
        "brain": brain,
        # What atlas may act on (always as a proposed plan, each step confirmed) vs only watch.
        "responsibility": {
            "containers": "restart / stop / resize",
            "proxmox_guests": "restart / shutdown / resize" if config.proxmox.enabled else "",
            "lan_hosts": "reachability checks only"
        }
    }
