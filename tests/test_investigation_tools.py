import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import pytest

from atlas.config.models import AtlasConfig
from atlas.discovery.host_health import get_host_health
from atlas.intelligence.tools import build_tools, execute_tool


class _FakeJellyfin(BaseHTTPRequestHandler):

    ROUTES = {
        "/Sessions": [{"UserName": "palma", "DeviceName": "Garage TV", "Client": "Jellyfin Android TV",
                       "RemoteEndPoint": "192.168.10.224", "NowPlayingItem": {"Name": "The Furious"},
                       "PlayState": {"PlayMethod": "DirectStream"}}],
        "/System/ActivityLog/Entries": {"Items": [
            {"Date": "2026-09-28T21:43", "Type": "VideoPlayback", "Name": "palma is playing The Furious on Garage TV"},
            {"Date": "2026-09-28T21:40", "Type": "SessionStarted", "Name": "bobby is online from Chrome"}]},
        "/Plugins": [{"Id": "tk", "Name": "Transcode Killer", "Version": "5.0.0.0", "Status": "Active"}],
        "/Plugins/tk/Configuration": {"MaxWidth": 1920, "MaxHeight": 1080},
        "/status.json": {"temp": 81, "state": "ok"},
    }

    def do_GET(self):

        path = self.path.split("?")[0]

        if self.headers.get("Authorization") != 'MediaBrowser Token="K"' and path != "/status.json":
            self.send_response(401)
            self.end_headers()
            return

        body = json.dumps(self.ROUTES[path]).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_server():

    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeJellyfin)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _jellyfin_tools(url):

    config = AtlasConfig()
    config.jellyfin.enabled = True
    config.jellyfin.url = url
    config.jellyfin.api_key = "K"
    return build_tools(config)


def test_jellyfin_tools_only_when_enabled():

    assert not {"get_jellyfin_sessions", "get_jellyfin_activity", "get_jellyfin_plugins"} & set(build_tools(AtlasConfig()))


def test_jellyfin_sessions_show_play_method(fake_server):

    result = execute_tool(_jellyfin_tools(fake_server), "get_jellyfin_sessions", {})

    assert result["sessions"][0]["device"] == "Garage TV"
    assert result["sessions"][0]["play_method"] == "DirectStream"


def test_jellyfin_activity_search_and_plugins_with_config(fake_server):

    tools = _jellyfin_tools(fake_server)

    activity = execute_tool(tools, "get_jellyfin_activity", {"search": "furious"})
    plugins = execute_tool(tools, "get_jellyfin_plugins", {})

    assert [e["name"] for e in activity["entries"]] == ["palma is playing The Furious on Garage TV"]
    assert plugins["plugins"][0]["configuration"] == {"MaxWidth": 1920, "MaxHeight": 1080}


def test_jellyfin_bad_key_is_a_tool_error_not_a_crash(fake_server):

    config = AtlasConfig()
    config.jellyfin.enabled, config.jellyfin.url, config.jellyfin.api_key = True, fake_server, "wrong"

    assert "error" in execute_tool(build_tools(config), "get_jellyfin_sessions", {})


def test_host_health_reads_real_host_and_status_feed(fake_server):

    health = get_host_health({"raid": fake_server + "/status.json", "dead": "http://127.0.0.1:1/x"})

    # CI runners are freshly booted: uptime can round to 0
    assert health["uptime_hours"] >= 0 and health["booted_at"].endswith("UTC") and health["cpu_count"] >= 1
    assert health["status_feeds"]["raid"] == {"temp": 81, "state": "ok"}
    assert "error" in health["status_feeds"]["dead"]


def _container_with_logs(text):

    container = MagicMock()
    container.name = "jellyfin"
    container.logs.return_value = text.encode()
    client = MagicMock()
    client.containers.get.return_value = container
    return client, container


def test_search_container_logs_counts_and_keeps_most_recent():

    lines = "\n".join(
        ["2026-09-28T21:00:00Z [INF] started"] +
        [f"2026-09-28T21:44:{i:02d}Z [WRN] TranscodeKiller: Killing transcode process" for i in range(30)]
    )
    client, container = _container_with_logs(lines)

    with patch("atlas.docker.manager.get_client", return_value=client):
        result = execute_tool(build_tools(AtlasConfig()), "search_container_logs",
                              {"container": "jellyfin", "pattern": "killing TRANSCODE", "since_minutes": 60})

    assert result["total_matches"] == 30
    assert result["first_match"].startswith("2026-09-28T21:44:00Z")
    assert container.logs.call_args.kwargs["timestamps"] is True


def test_search_container_logs_treats_bad_regex_as_text_and_caps_window():

    client, container = _container_with_logs("a [WRN( b\nplain\n")

    with patch("atlas.docker.manager.get_client", return_value=client), patch("time.time", return_value=10_000_000):
        from atlas.docker.manager import search_container_logs
        result = search_container_logs("jellyfin", "[WRN(", since_minutes=10**9)

    assert result["total_matches"] == 1
    assert result["since_minutes"] == 7 * 1440
    assert container.logs.call_args.kwargs["since"] == 10_000_000 - 7 * 1440 * 60
