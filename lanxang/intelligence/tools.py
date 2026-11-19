from dataclasses import dataclass
from typing import Callable

from lanxang.config.models import AtlasConfig
from lanxang.knowledge.queries import KnowledgeQueries


@dataclass
class ToolDefinition:

    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], dict]


EMPTY_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False
}


def _get_containers(arguments):

    from lanxang.docker import collect_containers

    return collect_containers()


def _get_services(arguments):

    from lanxang.docker import collect_containers
    from lanxang.services import detect_services

    data = collect_containers()

    return {
        "services": detect_services(data.get("containers", []))
    }


def _get_recent_events(arguments):

    events = KnowledgeQueries().recent_events()

    return {
        "events": [
            {
                "event_type": event.event_type,
                "source": event.source,
                "created_at": str(event.created_at)
            }
            for event in events
        ]
    }


def _get_last_analysis(arguments):

    return {
        "analysis": KnowledgeQueries().latest_analysis()
    }


def _get_container_logs(arguments):

    from lanxang.docker import get_container_logs

    tail = min(int(arguments.get("tail") or 100), 500)

    return get_container_logs(arguments["container"], tail=tail)


def _check_host(arguments):

    from lanxang.discovery.reachability import check_host

    return check_host(arguments["host"], arguments.get("ports"))


def _search_container_logs(arguments):

    from lanxang.docker.manager import search_container_logs

    return search_container_logs(
        arguments["container"],
        arguments["pattern"],
        since_minutes=arguments.get("since_minutes") or 1440
    )


def _host_health_handler(config: AtlasConfig):

    def handler(arguments):

        from lanxang.discovery.host_health import get_host_health

        return get_host_health(config.health.status_urls)

    return handler


def _jellyfin_handler(config: AtlasConfig, what):

    def handler(arguments):

        from lanxang import jellyfin

        if what == "sessions":
            return jellyfin.get_sessions(config.jellyfin)

        if what == "activity":
            return jellyfin.get_activity(
                config.jellyfin,
                limit=_limit(arguments.get("limit"), 50, 200),
                search=arguments.get("search") or ""
            )

        return jellyfin.get_plugins(config.jellyfin)

    return handler


def _notes_handler(config: AtlasConfig):

    def handler(arguments):

        from lanxang.knowledge.notes import search_notes

        limit = _limit(arguments.get("limit"), 5, 10)

        return search_notes(config.knowledge.notes_paths, arguments["query"], limit=limit)

    return handler


def _proxmox_handler(config: AtlasConfig):

    def handler(arguments):

        from lanxang.proxmox import connect, discover_nodes, discover_resources

        proxmox_settings = config.proxmox

        client = connect(
            proxmox_settings.host,
            proxmox_settings.user,
            password=proxmox_settings.password,
            token_name=proxmox_settings.token_name,
            token_value=proxmox_settings.token_value,
            verify_ssl=proxmox_settings.verify_ssl
        )

        if not client:
            return {"available": False}

        return {
            "available": True,
            "nodes": discover_nodes(client),
            "guests": discover_resources(client)
        }

    return handler


def _monitoring_handler(config: AtlasConfig):

    def handler(arguments):

        from lanxang.monitoring import collect_container_metrics, collect_metrics

        monitoring_settings = config.monitoring

        host_data = collect_metrics(monitoring_settings.prometheus_url)

        if not host_data["available"]:
            return host_data

        container_data = collect_container_metrics(
            monitoring_settings.prometheus_url
        )

        host_data["containers"] = container_data["containers"]

        return host_data

    return handler


def _limit(value, default: int, top: int) -> int:
    """A model's "limit" argument, clamped to 1..top; junk ("lots", None) means the default."""

    try:
        return max(1, min(int(value or default), top))
    except (TypeError, ValueError):
        return default


def _short(text, size: int = 300) -> str:

    text = text or ""
    return text if len(text) <= size else text[:size - 1] + "…"


def _cap(rows: list, limit: int = 40) -> dict:
    """Small local models choke on long lists: cap them and say how many were left out."""

    return {"items": rows[:limit], "more": max(0, len(rows) - limit)}


def _not_set_up(how):

    return {"status": "not set up", "how": how}


def _when(value):

    return value.isoformat() if hasattr(value, "isoformat") else value


def _posture_handler(config: AtlasConfig):

    def handler(arguments):

        from lanxang.clock import utcnow
        from lanxang.posture.model import build_posture
        from lanxang.posture.store import PostureStore

        store = PostureStore()

        if not config.posture.enabled or not store.statuses():
            return _not_set_up("Turn on posture.enabled (Setup page, Security card), then run lanxang posture watch.")

        data = build_posture(store, utcnow())
        routes = data["exposure"]

        return {
            "strip": [{k: item.get(k) for k in ("label", "state", "value", "detail")} for item in data["strip"]],
            "routes": len(routes),
            "unprotected": [r["name"] for r in routes if not r.get("protection")],
            "new_destinations": _cap([
                {"source": r["source"], "org": r["org"], "country": r["cc"], "first_seen": r["first_seen"]}
                for r in data["review"]
            ], 10)
        }

    return handler


def _devices_handler(config: AtlasConfig):

    def handler(arguments):

        from lanxang.devices.store import InventoryStore

        limit = _limit(arguments.get("limit"), 40, 40)
        which = arguments.get("filter") or "all"
        devices = InventoryStore().devices()

        if which == "new":
            devices = [d for d in devices if d["state"] == "new"]
        elif which == "quiet":
            devices = [d for d in devices if d["status"] == "quiet"]

        return _cap([
            {k: d.get(k) for k in ("name", "ip", "kind", "state", "status", "last_seen")} for d in devices
        ], limit)

    return handler


def _alerts_handler(config: AtlasConfig):

    def handler(arguments):

        from lanxang.alerts import AlertStore
        from lanxang.clock import utcnow

        listing = AlertStore().listing(utcnow(), 7)

        def rows(alerts):
            return [{"title": a["title"], "source": a["source"], "level": a["level"], "detail": _short(a["detail"]),
                     "opened_at": _when(a["opened_at"]), "acknowledged": a["acked_at"] is not None} for a in alerts]

        return {
            "open": _cap(rows(listing["open"] + listing["watch"])),
            "recently_resolved": _cap(rows(listing["resolved"]), 10)
        }

    return handler


def _disks_handler(config: AtlasConfig):

    def handler(arguments):

        from lanxang.posture.store import PostureStore
        from lanxang.web.metrics import _sources

        found = _sources()["disks"](PostureStore().statuses())
        disks = [{"host": host, **{k: disk.get(k) for k in ("dev", "model", "temp", "health", "life")}}
                 for host, listed in found for disk in listed]

        if not disks:
            return _not_set_up("Disk health comes from the Proxmox scan and the NAS card on the Setup page.")

        return _cap(disks)

    return handler


def _uptime_handler(config: AtlasConfig):

    def handler(arguments):

        from lanxang.clock import utcnow
        from lanxang.monitoring.uptime import UptimeStore

        names = [check.name for check in config.uptime.checks]

        if not names:
            return _not_set_up("Add uptime checks on the Servers > Uptime page.")

        summary = UptimeStore().summary(names, utcnow())

        return _cap([
            {"name": name, "up": last[1] if (last := info["last"]) else None, "uptime": info["uptime"],
             "last_failure": _when(info["last_failure"][0]) if info["last_failure"] else None}
            for name, info in summary.items()
        ])

    return handler


def _internet_view_handler(config: AtlasConfig):

    def handler(arguments):

        from lanxang.posture.store import PostureStore

        detail = (PostureStore().statuses().get("internet_view") or {}).get("detail")

        if not detail:
            return _not_set_up("Run lanxang internet check, or use the Setup page's Internet view card.")

        return {k: detail.get(k) for k in ("checked_at", "ip", "ok", "known", "ports", "vulns", "cpes", "error")}

    return handler


def build_tools(config: AtlasConfig) -> dict[str, ToolDefinition]:
    """
    Read-only tools an AI provider can call mid-request to pull live
    data beyond whatever fixed snapshot it was handed. Deliberately
    observation-only - no mutating action is ever exposed here, those
    stay behind their own approval-gated CLI commands (lanxang restart/
    stop/proxmox restart), same separation lanxang analyze's suggested
    actions already keep from execution.
    """

    tools = {
        "get_containers": ToolDefinition(
            name="get_containers",
            description=(
                "Get the current live list of Docker containers and "
                "their status."
            ),
            input_schema=EMPTY_SCHEMA,
            handler=_get_containers
        ),
        "get_services": ToolDefinition(
            name="get_services",
            description=(
                "Identify known self-hosted services (Plex, Sonarr, "
                "etc.) running in the current Docker containers."
            ),
            input_schema=EMPTY_SCHEMA,
            handler=_get_services
        ),
        "get_recent_events": ToolDefinition(
            name="get_recent_events",
            description=(
                "Get recently recorded Lanxang operational events "
                "(discoveries, scans, actions taken)."
            ),
            input_schema=EMPTY_SCHEMA,
            handler=_get_recent_events
        ),
        "get_last_analysis": ToolDefinition(
            name="get_last_analysis",
            description=(
                "Get the most recent previously saved AI analysis, "
                "if one exists."
            ),
            input_schema=EMPTY_SCHEMA,
            handler=_get_last_analysis
        ),
        "get_container_logs": ToolDefinition(
            name="get_container_logs",
            description=(
                "Get recent log lines for a specific Docker container. "
                "Use when reasoning from status alone isn't enough to "
                "explain what's actually happening."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "container": {
                        "type": "string",
                        "description": (
                            "Container name, as it appears in "
                            "get_containers."
                        )
                    },
                    "tail": {
                        "type": "integer",
                        "description": (
                            "Number of recent lines to fetch "
                            "(default 100, capped at 500)."
                        )
                    }
                },
                "required": ["container"],
                "additionalProperties": False
            },
            handler=_get_container_logs
        ),
        "check_host": ToolDefinition(
            name="check_host",
            description=(
                "Check whether a host on the network is reachable: DNS "
                "resolution plus which TCP ports accept a connection and "
                "how fast. Use to diagnose 'is X down or just one service'."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "Hostname or IP address."
                    },
                    "ports": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": (
                            "TCP ports to test (default 22, 80, 443; "
                            "max 10)."
                        )
                    }
                },
                "required": ["host"],
                "additionalProperties": False
            },
            handler=_check_host
        ),
        "search_container_logs": ToolDefinition(
            name="search_container_logs",
            description=(
                "Search a container's full log (not just the tail) for a "
                "word or regex over the last N minutes. Returns how many "
                "lines matched, when the first match was, and the most "
                "recent matches - use it to find warnings/errors and to "
                "see when a problem started."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "container": {
                        "type": "string",
                        "description": "Container name, as in get_containers."
                    },
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Word or regex, case-insensitive, e.g. "
                            "'error|warn' or 'killing transcode'."
                        )
                    },
                    "since_minutes": {
                        "type": "integer",
                        "description": "How far back to look (default 1440 = 24h, max 7 days)."
                    }
                },
                "required": ["container", "pattern"],
                "additionalProperties": False
            },
            handler=_search_container_logs
        ),
        "get_host_health": ToolDefinition(
            name="get_host_health",
            description=(
                "This host's vital signs: last boot time/uptime (spot "
                "unexpected restarts), load, memory, swap, root disk, "
                "hottest temperature per sensor, and configured status "
                "feeds such as the RAID card watchdog."
            ),
            input_schema=EMPTY_SCHEMA,
            handler=_host_health_handler(config)
        ),
    }

    if config.jellyfin.enabled:

        tools["get_jellyfin_sessions"] = ToolDefinition(
            name="get_jellyfin_sessions",
            description=(
                "Jellyfin playback right now: who is watching what, on "
                "which device/app, from which IP, and how - DirectPlay, "
                "DirectStream (remux) or Transcode, with transcode "
                "reasons. First stop for stutter/buffering complaints."
            ),
            input_schema=EMPTY_SCHEMA,
            handler=_jellyfin_handler(config, "sessions")
        )

        tools["get_jellyfin_activity"] = ToolDefinition(
            name="get_jellyfin_activity",
            description=(
                "Jellyfin's activity log, newest first: playback "
                "start/stop per user and device, logins, plugin installs. "
                "Use 'search' to see an item's history, e.g. whether a "
                "movie played fine before on the same device."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Only entries whose text contains this (e.g. a movie title)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries (default 50, max 200)."
                    }
                },
                "additionalProperties": False
            },
            handler=_jellyfin_handler(config, "activity")
        )

        tools["get_jellyfin_plugins"] = ToolDefinition(
            name="get_jellyfin_plugins",
            description=(
                "Installed Jellyfin plugins with version, status and live "
                "settings - plugins can silently change playback "
                "behavior (e.g. one that kills high-resolution transcodes)."
            ),
            input_schema=EMPTY_SCHEMA,
            handler=_jellyfin_handler(config, "plugins")
        )

    if config.knowledge.notes_paths:

        tools["search_notes"] = ToolDefinition(
            name="search_notes",
            description=(
                "Search the operator's own notes (runbooks, restore "
                "guides, host/service layout, past incidents and fixes) "
                "by keywords. Use before answering how this specific "
                "network is set up or how something was fixed before."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Keywords, e.g. 'jellyfin transcode' or "
                            "'raid card temperature'."
                        )
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max sections to return (default 5, max 10)."
                    }
                },
                "required": ["query"],
                "additionalProperties": False
            },
            handler=_notes_handler(config)
        )

    if config.proxmox.enabled:

        tools["get_proxmox_status"] = ToolDefinition(
            name="get_proxmox_status",
            description=(
                "Get the current live Proxmox cluster status: nodes "
                "and every VM/LXC guest."
            ),
            input_schema=EMPTY_SCHEMA,
            handler=_proxmox_handler(config)
        )

    if config.monitoring.enabled:

        tools["get_monitoring"] = ToolDefinition(
            name="get_monitoring",
            description=(
                "Query live Prometheus host and per-container "
                "CPU/memory/disk metrics."
            ),
            input_schema=EMPTY_SCHEMA,
            handler=_monitoring_handler(config)
        )

    tools.update({
        "get_posture": ToolDefinition(
            name="get_posture",
            description=(
                "Get the security posture: is the VPN protecting traffic, which public routes lack "
                "Authelia sign-in, and which new internet destinations need review."
            ),
            input_schema=EMPTY_SCHEMA,
            handler=_posture_handler(config)
        ),
        "get_devices": ToolDefinition(
            name="get_devices",
            description=(
                "List devices on the home network, answering which devices are new, "
                "quiet (not seen lately) or all known."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": ["all", "new", "quiet"],
                        "description": "all (default), new (not yet reviewed) or quiet (not seen lately)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max devices to return (default and max 40)."
                    }
                },
                "additionalProperties": False
            },
            handler=_devices_handler(config)
        ),
        "get_alerts": ToolDefinition(
            name="get_alerts",
            description="Get the open alerts and what was resolved this week, answering what is wrong right now.",
            input_schema=EMPTY_SCHEMA,
            handler=_alerts_handler(config)
        ),
        "get_disks": ToolDefinition(
            name="get_disks",
            description="Get disk health, temperature and wear for Proxmox nodes and the NAS, answering whether any disk is failing.",
            input_schema=EMPTY_SCHEMA,
            handler=_disks_handler(config)
        ),
        "get_uptime": ToolDefinition(
            name="get_uptime",
            description="Get up/down state and uptime percentages of the monitored services, answering what was down and for how long.",
            input_schema=EMPTY_SCHEMA,
            handler=_uptime_handler(config)
        )
    })

    if config.posture.internet_view:

        tools["get_internet_view"] = ToolDefinition(
            name="get_internet_view",
            description="Get what the internet can see on the home public IP (open ports, known vulnerabilities).",
            input_schema=EMPTY_SCHEMA,
            handler=_internet_view_handler(config)
        )

    return tools


def execute_tool(tools: dict[str, ToolDefinition] | None, name: str, arguments: dict) -> dict:
    """
    Dispatch a tool call by name. An unknown tool name or a handler
    exception becomes an {"error": ...} result rather than raising -
    a hallucinated tool name, or a live query that fails (e.g.
    Proxmox unreachable), shouldn't crash the whole analysis/chat
    session.
    """

    tools = tools or {}

    definition = tools.get(name)

    if not definition:

        return {"error": f"Unknown tool: {name}"}

    try:
        return definition.handler(arguments)

    except Exception as error:

        return {"error": str(error)}
