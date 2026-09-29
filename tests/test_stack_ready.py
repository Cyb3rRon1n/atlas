import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from atlas.config import loader
from atlas.config.loader import expand_env
from atlas.web.render import build_summary


def test_expand_env_braced_only_with_defaults():

    env = {"JF_KEY": "abc", "EMPTY": ""}

    assert expand_env("key: ${JF_KEY}", env) == "key: abc"
    assert expand_env("host: ${OLLAMA:-http://ollama:11434}", env) == "host: http://ollama:11434"
    assert expand_env("x: ${EMPTY:-fallback} y: ${MISSING}", env) == "x: fallback y: "
    assert expand_env("password: pa$word$HOME", env) == "password: pa$word$HOME"


def test_load_config_expands_environment(isolated_cwd, monkeypatch):

    monkeypatch.setenv("ATLAS_TEST_KEY", "k123")
    (isolated_cwd / "atlas.yaml").write_text(
        "jellyfin:\n  enabled: true\n  api_key: ${ATLAS_TEST_KEY}\nintelligence:\n  ollama_host: ${NOPE:-http://gpu:11434}\n")

    config = loader.load_config()

    assert config.jellyfin.api_key == "k123"
    assert config.intelligence.ollama_host == "http://gpu:11434"


def test_empty_config_file_is_defaults(isolated_cwd):

    (isolated_cwd / "atlas.yaml").write_text("")

    assert loader.load_config().name == "atlas-node"


def _topology(down=False, unhealthy=False):

    return {
        "generated_at": "2026-09-29 15:00:00 UTC",
        "docker": {"networks": {"proxy": [
            {"name": "jellyfin", "status": "running", "health": "unhealthy" if unhealthy else "healthy", "public": []},
            {"name": "old", "status": "exited", "health": "", "public": []}]}},
        "proxmox": {"guests": [{"name": "nas", "status": "running"}, {"name": "t", "status": "stopped", "template": True}]},
        "lan": [{"name": "nas", "reachable": True}, {"name": "tv", "reachable": not down}],
        "brain": {"reachable": True},
    }


def test_summary_counts_and_status():

    ok = build_summary(_topology())
    assert (ok["status"], ok["containers_running"], ok["containers_total"]) == ("ok", 1, 2)
    assert (ok["guests_running"], ok["guests_total"], ok["hosts_up"], ok["hosts_total"]) == (1, 1, 2, 2)

    bad = build_summary(_topology(down=True, unhealthy=True))
    assert bad["status"] == "degraded" and bad["hosts_down"] == ["tv"] and bad["containers_unhealthy"] == ["jellyfin"]

    assert "atlas map" in build_summary(None)["status"]


def test_api_summary_route_serves_json(monkeypatch):

    from atlas.web import server

    monkeypatch.setattr(server.KnowledgeQueries, "latest_topology", lambda self: _topology())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.AtlasWebHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/api/summary", timeout=5) as response:
            assert response.headers["Content-Type"] == "application/json"
            assert json.load(response)["containers_total"] == 2
    finally:
        httpd.shutdown()
