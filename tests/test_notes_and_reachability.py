import socket

from atlas.config.models import AtlasConfig
from atlas.discovery.reachability import check_host
from atlas.intelligence.tools import build_tools, execute_tool
from atlas.knowledge.notes import search_notes


def _notes(tmp_path):

    (tmp_path / "jellyfin.md").write_text(
        "# Jellyfin\n\nIntro.\n\n## Transcode Killer\n\nKills >1080p transcodes, disabled 2026-09-28.\n\n"
        "## Networking\n\nLAN networks 192.168.10.0/24, known proxies traefik.\n"
    )
    (tmp_path / "raid.txt").write_text("RAID card runs 82-87C; watchdog stops the stack at 100C.\n")
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "HEAD.md").write_text("transcode transcode transcode\n")

    return tmp_path


def test_search_notes_ranks_heading_match_first_and_skips_hidden_dirs(tmp_path):

    result = search_notes([str(_notes(tmp_path))], "transcode killer")

    assert result["results"][0]["section"] == "Transcode Killer"
    assert all(".git" not in hit["file"] for hit in result["results"])


def test_search_notes_prefers_sections_matching_more_terms(tmp_path):

    result = search_notes([str(_notes(tmp_path))], "raid watchdog temperature")

    assert result["results"][0]["file"].endswith("raid.txt")


def test_search_notes_empty_query_and_missing_path(tmp_path):

    assert search_notes([str(tmp_path)], "  ")["results"] == []
    assert search_notes([str(tmp_path / "nope")], "jellyfin") == {"results": []}


def test_search_notes_tool_only_offered_when_configured(tmp_path):

    assert "search_notes" not in build_tools(AtlasConfig())

    config = AtlasConfig()
    config.knowledge.notes_paths = [str(_notes(tmp_path))]
    tools = build_tools(config)

    result = execute_tool(tools, "search_notes", {"query": "known proxies", "limit": 50})

    assert result["results"][0]["section"] == "Networking"


def test_check_host_reports_open_and_closed_ports_on_a_real_socket():

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    open_port = listener.getsockname()[1]

    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    closed_port = closed.getsockname()[1]
    closed.close()

    try:
        result = check_host("127.0.0.1", [open_port, closed_port], timeout=1)

    finally:
        listener.close()

    assert result["reachable"] is True
    assert [p["open"] for p in result["ports"]] == [True, False]


def test_check_host_unresolvable_name_and_port_cap():

    assert check_host("no-such-host.invalid")["resolved"] is False
    assert len(check_host("127.0.0.1", list(range(1, 30)), timeout=0.2)["ports"]) == 10


def test_check_host_is_always_offered():

    assert "check_host" in build_tools(AtlasConfig())


def test_search_notes_keeps_scripts_whole(tmp_path):

    (tmp_path / "raid-card-watchdog.sh").write_text("#!/bin/bash\n# stops the stack at 100C\n# second comment\nTEMP=100\n")

    result = search_notes([str(tmp_path)], "raid watchdog")

    assert len(result["results"]) == 1
    assert "second comment" in result["results"][0]["excerpt"]
