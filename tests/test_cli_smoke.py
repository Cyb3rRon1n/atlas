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


def test_analyze_prints_suggested_action_for_known_container_only(
    isolated_cwd, temp_db
):
    """
    Seeds an environment with one known container ('plex'), then has
    the (mocked) AI provider return one recommendation targeting that
    real container and one targeting a container Atlas never observed
    ('ghost'). Only the grounded suggestion should be printed - this
    exercises the real AtlasAnalyzer cross-check, not a mocked one.
    """

    from atlas.intelligence.context import AtlasEnvironmentContext
    from atlas.intelligence.providers.base import (
        AIProvider,
        AnalysisResult,
        Recommendation,
        SuggestedAction,
    )
    from atlas.knowledge.store import KnowledgeStore

    environment = AtlasEnvironmentContext()

    environment.update(
        "containers",
        {"Docker": {"available": True, "containers": [{"name": "plex"}]}}
    )

    KnowledgeStore().save_environment(environment)

    class FakeProvider(AIProvider):

        def analyze(self, context):

            return AnalysisResult(
                summary="One host, lightly loaded.",
                recommendations=[
                    Recommendation(
                        title="Container 'plex' looks unhealthy",
                        detail="Restarted 4 times in the last hour.",
                        severity="warning",
                        action=SuggestedAction(
                            type="restart_container", target="plex"
                        )
                    ),
                    Recommendation(
                        title="Container 'ghost' looks unhealthy",
                        detail="This container was never actually observed.",
                        severity="warning",
                        action=SuggestedAction(
                            type="restart_container", target="ghost"
                        )
                    ),
                ]
            )

    with patch(
        "atlas.cli.main.get_provider",
        return_value=FakeProvider()
    ):

        result = runner.invoke(app, ["analyze"])

    assert result.exit_code == 0
    assert "Suggested: atlas restart plex" in result.output
    assert "atlas restart ghost" not in result.output


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


PROXMOX_ENABLED_ATLAS_YAML = (
    "proxmox:\n"
    "  enabled: true\n"
    "  host: proxmox.local\n"
    "  user: root@pam\n"
    "  password: hunter2\n"
)


def test_proxmox_scan_first_run_prints_no_changes_section(isolated_cwd, temp_db):
    """
    With no prior environment saved, there's no baseline to diff
    against - the changes section should be skipped entirely rather
    than claiming "no changes" (which implies a comparison happened).
    """

    (isolated_cwd / "atlas.yaml").write_text(PROXMOX_ENABLED_ATLAS_YAML)

    with (
        patch("atlas.cli.main.connect", return_value=MagicMock()),
        patch(
            "atlas.cli.main.discover_nodes",
            return_value=[{"name": "pve1", "status": "online"}]
        ),
        patch(
            "atlas.cli.main.discover_resources",
            return_value=[
                {
                    "vmid": 100, "name": "plex", "node": "pve1", "type": "qemu",
                    "status": "running", "cpu": 0.1, "maxcpu": 4, "mem": 100,
                    "maxmem": 1000, "disk": 0, "maxdisk": 0, "uptime": 10
                }
            ]
        )
    ):

        result = runner.invoke(app, ["proxmox", "scan"])

    assert result.exit_code == 0
    assert "Changes since last scan" not in result.output
    assert "No changes since last scan." not in result.output


def test_proxmox_scan_second_run_reports_changes(isolated_cwd, temp_db):

    (isolated_cwd / "atlas.yaml").write_text(PROXMOX_ENABLED_ATLAS_YAML)

    first_guests = [
        {
            "vmid": 100, "name": "plex", "node": "pve1", "type": "qemu",
            "status": "running", "cpu": 0.1, "maxcpu": 4, "mem": 100,
            "maxmem": 1000, "disk": 0, "maxdisk": 0, "uptime": 10
        }
    ]

    second_guests = [
        {
            "vmid": 100, "name": "plex", "node": "pve1", "type": "qemu",
            "status": "stopped", "cpu": 0.0, "maxcpu": 4, "mem": 0,
            "maxmem": 1000, "disk": 0, "maxdisk": 0, "uptime": 0
        }
    ]

    with (
        patch("atlas.cli.main.connect", return_value=MagicMock()),
        patch(
            "atlas.cli.main.discover_nodes",
            return_value=[{"name": "pve1", "status": "online"}]
        ),
        patch(
            "atlas.cli.main.discover_resources",
            side_effect=[first_guests, second_guests]
        )
    ):

        first_result = runner.invoke(app, ["proxmox", "scan"])
        second_result = runner.invoke(app, ["proxmox", "scan"])

    assert first_result.exit_code == 0
    assert second_result.exit_code == 0

    assert "Changes since last scan:" in second_result.output
    assert (
        "Guest 'plex' (100) status changed: running → stopped"
        in second_result.output
    )

    event_types = [
        event.event_type for event in KnowledgeQueries().recent_events()
    ]

    assert "atlas.proxmox.changes_detected" in event_types


def test_monitor_when_disabled_does_not_attempt_connection(isolated_cwd):
    """
    monitoring.enabled defaults to false - this is the actual
    experience today, since no Prometheus is configured yet.
    """

    result = runner.invoke(app, ["monitor"])

    assert result.exit_code == 0
    assert "Monitoring integration disabled." in result.output


def test_monitor_when_enabled_saves_metrics_to_environment(
    isolated_cwd, temp_db
):

    (isolated_cwd / "atlas.yaml").write_text(
        "monitoring:\n"
        "  enabled: true\n"
        "  prometheus_url: http://localhost:9090\n"
    )

    def fake_get(url, params=None, timeout=None):

        response = MagicMock()

        response.json.return_value = {
            "status": "success",
            "data": {"result": [{"value": [0, "12.3"]}]}
        }

        return response

    with patch("requests.get", side_effect=fake_get):

        result = runner.invoke(app, ["monitor"])

    assert result.exit_code == 0
    assert "Monitoring scan complete" in result.output

    environment = KnowledgeQueries().latest_environment()

    assert environment["monitoring"]["available"] is True
    assert environment["monitoring"]["metrics"]["cpu_percent"] == 12.3


def test_discover_persists_both_builtin_and_plugin_data(isolated_cwd, temp_db):
    """
    atlas discover now runs built-in discovery and plugin discovery in
    one pass. This checks both halves land in the same saved
    environment snapshot, not just that the command exits cleanly -
    the whole point of merging discover-plugins into discover was that
    one command produces one complete picture.
    """

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.image.tags = ["plexinc/pms-docker"]
    fake_container.status = "running"
    fake_container.short_id = "abc123"

    with (
        patch(
            "atlas.discovery.network.socket.gethostbyname_ex",
            return_value=("sentinel", [], ["192.168.1.10"])
        ),
        patch("atlas.docker.manager.docker.from_env") as mock_from_env
    ):

        mock_from_env.return_value.containers.list.return_value = [
            fake_container
        ]

        result = runner.invoke(app, ["discover"])

    assert result.exit_code == 0
    assert "Discovery complete" in result.output
    assert "Plugins discovered:" in result.output

    environment = KnowledgeQueries().latest_environment()

    assert "hostname" in environment["system"]
    assert "cpu" in environment["hardware"]
    assert environment["containers"]["Docker"]["available"] is True
    assert environment["containers"]["Docker"]["containers"][0]["name"] == "plex"


def test_restart_declined_does_not_restart_container(isolated_cwd, temp_db):

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.image.tags = ["plexinc/pms-docker"]
    fake_container.status = "exited"

    with patch("atlas.docker.manager.docker.from_env") as mock_from_env:

        mock_from_env.return_value.containers.get.return_value = fake_container

        result = runner.invoke(app, ["restart", "plex"], input="n\n")

    assert result.exit_code == 0
    assert "Cancelled." in result.output
    fake_container.restart.assert_not_called()


def test_restart_confirmed_restarts_container_and_logs_event(
    isolated_cwd, temp_db
):

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.image.tags = ["plexinc/pms-docker"]
    fake_container.status = "exited"

    with patch("atlas.docker.manager.docker.from_env") as mock_from_env:

        mock_from_env.return_value.containers.get.return_value = fake_container

        result = runner.invoke(app, ["restart", "plex"], input="y\n")

    assert result.exit_code == 0
    assert "restarted" in result.output
    fake_container.restart.assert_called_once_with()

    events = KnowledgeQueries().recent_events()

    assert events[0].event_type == "atlas.action.container_restarted"
