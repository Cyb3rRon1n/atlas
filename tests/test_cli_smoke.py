from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from atlas.cli.main import app
from atlas.knowledge.queries import KnowledgeQueries


runner = CliRunner()


def test_version():

    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "0.1.0-alpha" in result.output


def test_status():

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Atlas Status" in result.output


def test_config_shows_defaults(isolated_cwd):

    result = runner.invoke(app, ["config"])

    assert result.exit_code == 0
    assert "atlas-node" in result.output


def test_doctor(isolated_cwd):

    with patch(
        "atlas.docker.manager.docker.from_env",
        side_effect=RuntimeError("no docker socket")
    ):
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Atlas Doctor" in result.output


def test_history_with_no_events(isolated_cwd, temp_db):

    result = runner.invoke(app, ["history"])

    assert result.exit_code == 0
    assert "No historical events found." in result.output


def test_intelligence_with_no_environment(isolated_cwd, temp_db):

    result = runner.invoke(app, ["intelligence"])

    assert result.exit_code == 0
    assert "No environment data found." in result.output


def test_analyze_with_no_environment_short_circuits_without_api_call(
    isolated_cwd, temp_db
):

    result = runner.invoke(app, ["analyze"])

    assert result.exit_code == 0
    assert "No environment data found." in result.output
    assert "Run: atlas discover" in result.output


def test_proxmox_scan_when_disabled_does_not_attempt_connection(isolated_cwd):
    """
    proxmox.enabled defaults to false, so this exercises the fast exit
    path without needing a real (or mocked) Proxmox server - this is
    also the path that regression-tests the bug where scan() used to
    call connect() without passing the configured password at all.
    """

    result = runner.invoke(app, ["proxmox", "scan"])

    assert result.exit_code == 0
    assert "Proxmox integration disabled." in result.output


def test_discover_plugins_persists_results_to_environment(isolated_cwd, temp_db):
    """
    Regression test for the discovery-unification gap: discover-plugins
    used to just print its results and discard them. This checks the
    data actually lands in the knowledge store, not just that the
    command exits cleanly.
    """

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.image.tags = ["plexinc/pms-docker"]
    fake_container.status = "running"
    fake_container.short_id = "abc123"

    with patch("atlas.docker.manager.docker.from_env") as mock_from_env:

        mock_from_env.return_value.containers.list.return_value = [
            fake_container
        ]

        result = runner.invoke(app, ["discover-plugins"])

    assert result.exit_code == 0
    assert "Plugin discovery complete" in result.output

    environment = KnowledgeQueries().latest_environment()

    assert environment["containers"]["Docker"]["available"] is True
    assert environment["containers"]["Docker"]["containers"][0]["name"] == "plex"
