from unittest.mock import patch

from atlas.config.models import AtlasConfig
from atlas.intelligence.tools import ToolDefinition, build_tools, execute_tool


def test_build_tools_always_includes_base_tools():

    tools = build_tools(AtlasConfig())

    assert "get_containers" in tools
    assert "get_services" in tools
    assert "get_recent_events" in tools
    assert "get_last_analysis" in tools


def test_build_tools_excludes_proxmox_and_monitoring_when_disabled():

    tools = build_tools(AtlasConfig())

    assert "get_proxmox_status" not in tools
    assert "get_monitoring" not in tools


def test_build_tools_includes_proxmox_when_enabled():

    config = AtlasConfig()
    config.proxmox.enabled = True

    tools = build_tools(config)

    assert "get_proxmox_status" in tools


def test_build_tools_includes_monitoring_when_enabled():

    config = AtlasConfig()
    config.monitoring.enabled = True

    tools = build_tools(config)

    assert "get_monitoring" in tools


def test_get_containers_tool_wraps_collect_containers():

    tools = build_tools(AtlasConfig())

    with patch(
        "atlas.docker.collect_containers",
        return_value={"available": True, "containers": [{"name": "plex"}]}
    ):

        result = execute_tool(tools, "get_containers", {})

    assert result == {"available": True, "containers": [{"name": "plex"}]}


def test_execute_tool_returns_error_for_unknown_tool_name():

    tools = build_tools(AtlasConfig())

    result = execute_tool(tools, "delete_everything", {})

    assert "error" in result


def test_execute_tool_returns_error_when_tools_is_none():

    result = execute_tool(None, "get_containers", {})

    assert "error" in result


def test_get_services_tool_detects_known_service_in_live_containers():

    tools = build_tools(AtlasConfig())

    with patch(
        "atlas.docker.collect_containers",
        return_value={
            "available": True,
            "containers": [{"name": "jellyfin", "status": "running"}]
        }
    ):

        result = execute_tool(tools, "get_services", {})

    assert result["services"][0]["name"] == "jellyfin"


def test_get_recent_events_tool_reads_from_knowledge_store(temp_db):

    from atlas.events import AtlasEvent
    from atlas.knowledge.store import KnowledgeStore

    KnowledgeStore().save_event(
        AtlasEvent(
            event_type="atlas.discovery.completed",
            source="Discovery",
            payload={}
        )
    )

    tools = build_tools(AtlasConfig())

    result = execute_tool(tools, "get_recent_events", {})

    assert result["events"][0]["event_type"] == "atlas.discovery.completed"
    assert result["events"][0]["source"] == "Discovery"


def test_get_last_analysis_tool_returns_none_when_nothing_saved(temp_db):

    tools = build_tools(AtlasConfig())

    result = execute_tool(tools, "get_last_analysis", {})

    assert result == {"analysis": None}


def test_get_proxmox_status_tool_reports_unavailable_when_connect_fails():

    config = AtlasConfig()
    config.proxmox.enabled = True

    tools = build_tools(config)

    with patch("atlas.proxmox.connect", return_value=None):

        result = execute_tool(tools, "get_proxmox_status", {})

    assert result == {"available": False}


def test_get_proxmox_status_tool_reports_nodes_and_guests():

    config = AtlasConfig()
    config.proxmox.enabled = True

    tools = build_tools(config)

    with patch("atlas.proxmox.connect", return_value=object()), \
         patch("atlas.proxmox.discover_nodes", return_value=[{"name": "pve1", "status": "online"}]), \
         patch("atlas.proxmox.discover_resources", return_value=[{"vmid": 100, "name": "plex"}]):

        result = execute_tool(tools, "get_proxmox_status", {})

    assert result["available"] is True
    assert result["nodes"][0]["name"] == "pve1"
    assert result["guests"][0]["vmid"] == 100


def test_get_monitoring_tool_reports_unavailable_when_prometheus_unreachable():

    config = AtlasConfig()
    config.monitoring.enabled = True

    tools = build_tools(config)

    with patch(
        "atlas.monitoring.collect_metrics",
        return_value={"available": False, "metrics": {}}
    ):

        result = execute_tool(tools, "get_monitoring", {})

    assert result == {"available": False, "metrics": {}}


def test_get_monitoring_tool_merges_host_and_container_metrics():

    config = AtlasConfig()
    config.monitoring.enabled = True

    tools = build_tools(config)

    with patch(
        "atlas.monitoring.collect_metrics",
        return_value={"available": True, "metrics": {"cpu_percent": 10.0}}
    ), patch(
        "atlas.monitoring.collect_container_metrics",
        return_value={"available": True, "containers": {"plex": {"cpu_percent": 2.0}}}
    ):

        result = execute_tool(tools, "get_monitoring", {})

    assert result["metrics"]["cpu_percent"] == 10.0
    assert result["containers"]["plex"]["cpu_percent"] == 2.0


def test_execute_tool_catches_handler_exception():

    def broken_handler():
        raise RuntimeError("boom")

    tools = {
        "broken": ToolDefinition(
            name="broken",
            description="always fails",
            input_schema={"type": "object", "properties": {}},
            handler=broken_handler
        )
    }

    result = execute_tool(tools, "broken", {})

    assert result == {"error": "boom"}
