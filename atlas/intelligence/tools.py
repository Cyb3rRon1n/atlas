from dataclasses import dataclass
from typing import Callable

from atlas.config.models import AtlasConfig
from atlas.knowledge.queries import KnowledgeQueries


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

    from atlas.docker import collect_containers

    return collect_containers()


def _get_services(arguments):

    from atlas.docker import collect_containers
    from atlas.services import detect_services

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

    from atlas.docker import get_container_logs

    tail = min(int(arguments.get("tail") or 100), 500)

    return get_container_logs(arguments["container"], tail=tail)


def _proxmox_handler(config: AtlasConfig):

    def handler(arguments):

        from atlas.proxmox import connect, discover_nodes, discover_resources

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

        from atlas.monitoring import collect_container_metrics, collect_metrics

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


def build_tools(config: AtlasConfig) -> dict[str, ToolDefinition]:
    """
    Read-only tools an AI provider can call mid-request to pull live
    data beyond whatever fixed snapshot it was handed. Deliberately
    observation-only - no mutating action is ever exposed here, those
    stay behind their own approval-gated CLI commands (atlas restart/
    stop/proxmox restart), same separation atlas analyze's suggested
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
                "Get recently recorded Atlas operational events "
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
    }

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
