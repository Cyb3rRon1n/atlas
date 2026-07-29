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


def test_init_declining_every_integration_writes_minimal_config(isolated_cwd):

    result = runner.invoke(
        app,
        ["init"],
        input="sentinel\nn\nanthropic\nclaude-opus-5\nn\ny\n"
    )

    assert result.exit_code == 0
    assert "atlas.yaml created" in result.output

    written = (isolated_cwd / "atlas.yaml").read_text()

    assert "name: sentinel" in written
    assert "enabled: false" in written

    log_files = list((isolated_cwd / "logs").glob("atlas-init-*.log"))

    assert len(log_files) == 1
    assert "name: sentinel" in log_files[0].read_text()
    assert "proxmox: disabled" in log_files[0].read_text()


def test_init_with_proxmox_token_auth_redacts_secret_from_log(isolated_cwd):

    result = runner.invoke(
        app,
        ["init"],
        input=(
            "sentinel\n"
            "y\n192.168.1.10\natlas@pve\ny\natlas-token\nsupersecret\nn\n"
            "anthropic\nclaude-opus-5\n"
            "n\ny\n"
        )
    )

    assert result.exit_code == 0

    written = (isolated_cwd / "atlas.yaml").read_text()

    assert "token_value: supersecret" in written
    assert "host: 192.168.1.10" in written
    # The review screen shows the length, not the value - the value itself
    # is expected in result.output too (it's the terminal session, not
    # hidden input); the file this test name is actually about is the log.
    assert "11 characters entered" in result.output

    log_text = (
        list((isolated_cwd / "logs").glob("atlas-init-*.log"))[0].read_text()
    )

    assert "supersecret" not in log_text
    assert "auth=token" in log_text


def test_init_with_proxmox_password_auth(isolated_cwd):

    result = runner.invoke(
        app,
        ["init"],
        input=(
            "sentinel\n"
            "y\n192.168.1.10\natlas@pve\nn\nhunter2\nn\n"
            "anthropic\nclaude-opus-5\n"
            "n\ny\n"
        )
    )

    assert result.exit_code == 0

    written = (isolated_cwd / "atlas.yaml").read_text()

    assert "password: hunter2" in written
    assert "token_value: ''" in written


def test_init_with_ollama_provider(isolated_cwd):

    result = runner.invoke(
        app,
        ["init"],
        input=(
            "sentinel\nn\n"
            "ollama\nhttp://localhost:11434\nllama3.1\n"
            "n\ny\n"
        )
    )

    assert result.exit_code == 0

    written = (isolated_cwd / "atlas.yaml").read_text()

    assert "provider: ollama" in written
    assert "model: llama3.1" in written


def test_init_reprompts_on_invalid_provider(isolated_cwd):

    result = runner.invoke(
        app,
        ["init"],
        input="sentinel\nn\nbogus\nanthropic\nclaude-opus-5\nn\ny\n"
    )

    assert result.exit_code == 0
    assert "Please enter 'anthropic' or 'ollama'." in result.output

    written = (isolated_cwd / "atlas.yaml").read_text()

    assert "provider: anthropic" in written


def test_init_declines_overwrite_of_existing_config(isolated_cwd):

    (isolated_cwd / "atlas.yaml").write_text("name: untouched\n")

    result = runner.invoke(app, ["init"], input="n\n")

    assert result.exit_code == 0
    assert "Cancelled." in result.output
    assert (isolated_cwd / "atlas.yaml").read_text() == "name: untouched\n"
    assert not (isolated_cwd / "logs").exists()


def test_init_confirms_overwrite_of_existing_config(isolated_cwd):

    (isolated_cwd / "atlas.yaml").write_text("name: untouched\n")

    result = runner.invoke(
        app,
        ["init"],
        input="y\nreplaced\nn\nanthropic\nclaude-opus-5\nn\ny\n"
    )

    assert result.exit_code == 0

    written = (isolated_cwd / "atlas.yaml").read_text()

    assert "name: replaced" in written


def test_init_declining_review_writes_nothing(isolated_cwd):
    """
    The review screen is the safety net for input that looked garbled
    while typing (e.g. a terminal that doesn't render backspace
    cleanly) - declining it must leave no atlas.yaml and no log,
    same as declining anything else.
    """

    result = runner.invoke(
        app,
        ["init"],
        input="sentinel\nn\nanthropic\nclaude-opus-5\nn\nn\n"
    )

    assert result.exit_code == 0
    assert "Cancelled - nothing written." in result.output
    assert not (isolated_cwd / "atlas.yaml").exists()
    assert not (isolated_cwd / "logs").exists()


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

        def analyze(self, context, tools=None):

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


def test_analyze_prints_suggested_stop_command_for_known_container(
    isolated_cwd, temp_db
):

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

        def analyze(self, context, tools=None):

            return AnalysisResult(
                summary="One host, lightly loaded.",
                recommendations=[
                    Recommendation(
                        title="Container 'plex' is consuming excessive resources",
                        detail="CPU usage has been pinned for an hour.",
                        severity="warning",
                        action=SuggestedAction(
                            type="stop_container", target="plex"
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
    assert "Suggested: atlas stop plex" in result.output


def test_chat_prints_reply_and_suggested_action(isolated_cwd, temp_db):

    from atlas.intelligence.providers.base import (
        AIProvider,
        ChatReply,
        SuggestedAction,
    )

    class FakeProvider(AIProvider):

        def analyze(self, context, tools=None):
            raise NotImplementedError

        def converse(self, messages, tools=None):

            return ChatReply(
                text="Plex is using a lot of CPU right now.",
                action=SuggestedAction(type="stop_container", target="plex")
            )

    with patch(
        "atlas.cli.main.get_provider",
        return_value=FakeProvider()
    ), patch(
        "atlas.docker.collect_containers",
        return_value={"available": True, "containers": [{"name": "plex"}]}
    ):

        result = runner.invoke(app, ["chat"], input="how's plex?\nexit\n")

    assert result.exit_code == 0
    assert "Plex is using a lot of CPU right now." in result.output
    assert "Suggested: atlas stop plex" in result.output


def test_chat_drops_suggested_action_for_hallucinated_container(
    isolated_cwd, temp_db
):

    from atlas.intelligence.providers.base import (
        AIProvider,
        ChatReply,
        SuggestedAction,
    )

    class FakeProvider(AIProvider):

        def analyze(self, context, tools=None):
            raise NotImplementedError

        def converse(self, messages, tools=None):

            return ChatReply(
                text="I'd stop ghost.",
                action=SuggestedAction(type="stop_container", target="ghost")
            )

    with patch(
        "atlas.cli.main.get_provider",
        return_value=FakeProvider()
    ), patch(
        "atlas.docker.collect_containers",
        return_value={"available": True, "containers": [{"name": "plex"}]}
    ):

        result = runner.invoke(app, ["chat"], input="how's ghost?\nexit\n")

    assert result.exit_code == 0
    assert "Suggested:" not in result.output


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


def test_proxmox_restart_when_disabled_does_not_attempt_connection(isolated_cwd):

    result = runner.invoke(app, ["proxmox", "restart", "100"])

    assert result.exit_code == 0
    assert "Proxmox integration disabled." in result.output


def test_proxmox_restart_guest_not_found(isolated_cwd):

    (isolated_cwd / "atlas.yaml").write_text(PROXMOX_ENABLED_ATLAS_YAML)

    with (
        patch("atlas.cli.main.connect", return_value=MagicMock()),
        patch("atlas.proxmox.manager.discover_resources", return_value=[]),
    ):

        result = runner.invoke(app, ["proxmox", "restart", "999"])

    assert result.exit_code == 0
    assert "No guest with vmid 999 found" in result.output


PROXMOX_GUEST = {
    "vmid": 100, "name": "plex", "node": "pve1", "type": "qemu",
    "status": "running", "cpu": 0.1, "maxcpu": 4, "mem": 100,
    "maxmem": 1000, "disk": 0, "maxdisk": 0, "uptime": 10
}


def test_proxmox_restart_declined_does_not_restart_guest(isolated_cwd):

    (isolated_cwd / "atlas.yaml").write_text(PROXMOX_ENABLED_ATLAS_YAML)

    with (
        patch("atlas.cli.main.connect", return_value=MagicMock()),
        patch(
            "atlas.proxmox.manager.discover_resources",
            return_value=[PROXMOX_GUEST]
        ),
        patch("atlas.cli.main.restart_guest") as mock_restart,
    ):

        result = runner.invoke(
            app, ["proxmox", "restart", "100"], input="n\n"
        )

    assert result.exit_code == 0
    assert "Cancelled." in result.output
    mock_restart.assert_not_called()


def test_proxmox_restart_confirmed_restarts_guest_and_logs_event(
    isolated_cwd, temp_db
):

    (isolated_cwd / "atlas.yaml").write_text(PROXMOX_ENABLED_ATLAS_YAML)

    with (
        patch("atlas.cli.main.connect", return_value=MagicMock()),
        patch(
            "atlas.proxmox.manager.discover_resources",
            return_value=[PROXMOX_GUEST]
        ),
        patch(
            "atlas.cli.main.restart_guest",
            return_value={"success": True}
        ) as mock_restart,
    ):

        result = runner.invoke(
            app, ["proxmox", "restart", "100"], input="y\n"
        )

    assert result.exit_code == 0
    assert "restarted" in result.output
    assert mock_restart.call_args.args[1:] == ("pve1", 100, "qemu")

    events = KnowledgeQueries().recent_events()

    assert events[0].event_type == "atlas.action.guest_restarted"


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


def test_monitor_flags_metric_over_threshold_and_publishes_event(
    isolated_cwd, temp_db
):

    (isolated_cwd / "atlas.yaml").write_text(
        "monitoring:\n"
        "  enabled: true\n"
        "  prometheus_url: http://localhost:9090\n"
        "  cpu_threshold: 80\n"
    )

    def fake_get(url, params=None, timeout=None):

        response = MagicMock()

        response.json.return_value = {
            "status": "success",
            "data": {"result": [{"value": [0, "92.0"]}]}
        }

        return response

    with patch("requests.get", side_effect=fake_get):

        result = runner.invoke(app, ["monitor"])

    assert result.exit_code == 0
    assert "cpu_percent: 92.0% (threshold: 80.0%)" in result.output

    event_types = [
        event.event_type for event in KnowledgeQueries().recent_events()
    ]

    assert "atlas.monitoring.threshold_exceeded" in event_types


def test_monitor_does_not_publish_threshold_event_when_nothing_exceeds(
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

    event_types = [
        event.event_type for event in KnowledgeQueries().recent_events()
    ]

    assert "atlas.monitoring.threshold_exceeded" not in event_types


def test_monitor_saves_container_metrics_to_environment(isolated_cwd, temp_db):

    (isolated_cwd / "atlas.yaml").write_text(
        "monitoring:\n"
        "  enabled: true\n"
        "  prometheus_url: http://localhost:9090\n"
    )

    def fake_get(url, params=None, timeout=None):

        query = params["query"]
        response = MagicMock()

        if "container_cpu_usage_seconds_total" in query:
            result = [{"metric": {"name": "plex"}, "value": [0, "25.0"]}]

        elif "container_memory_usage_bytes" in query:
            result = [{"metric": {"name": "plex"}, "value": [0, "40.0"]}]

        else:
            result = [{"value": [0, "12.3"]}]

        response.json.return_value = {
            "status": "success",
            "data": {"result": result}
        }

        return response

    with patch("requests.get", side_effect=fake_get):

        result = runner.invoke(app, ["monitor"])

    assert result.exit_code == 0
    assert "plex" in result.output

    environment = KnowledgeQueries().latest_environment()

    assert environment["monitoring"]["containers"]["plex"] == {
        "cpu_percent": 25.0,
        "memory_percent": 40.0
    }


def test_monitor_publishes_changes_detected_event_when_metric_crosses_since_last_scan(
    isolated_cwd, temp_db
):

    (isolated_cwd / "atlas.yaml").write_text(
        "monitoring:\n"
        "  enabled: true\n"
        "  prometheus_url: http://localhost:9090\n"
        "  cpu_threshold: 80\n"
    )

    def make_fake_get(host_value):

        def fake_get(url, params=None, timeout=None):

            query = params["query"]
            response = MagicMock()

            if "container_" in query:
                result = []

            else:
                result = [{"value": [0, host_value]}]

            response.json.return_value = {
                "status": "success",
                "data": {"result": result}
            }

            return response

        return fake_get

    with patch("requests.get", side_effect=make_fake_get("50.0")):
        first = runner.invoke(app, ["monitor"])

    assert first.exit_code == 0

    with patch("requests.get", side_effect=make_fake_get("92.0")):
        second = runner.invoke(app, ["monitor"])

    assert second.exit_code == 0
    assert "Changes since last scan" in second.output

    event_types = [
        event.event_type for event in KnowledgeQueries().recent_events()
    ]

    assert "atlas.monitoring.changes_detected" in event_types


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


def test_stop_declined_does_not_stop_container(isolated_cwd, temp_db):

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.image.tags = ["plexinc/pms-docker"]
    fake_container.status = "running"

    with patch("atlas.docker.manager.docker.from_env") as mock_from_env:

        mock_from_env.return_value.containers.get.return_value = fake_container

        result = runner.invoke(app, ["stop", "plex"], input="n\n")

    assert result.exit_code == 0
    assert "Cancelled." in result.output
    fake_container.stop.assert_not_called()


def test_stop_confirmed_stops_container_and_logs_event(
    isolated_cwd, temp_db
):

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.image.tags = ["plexinc/pms-docker"]
    fake_container.status = "running"

    with patch("atlas.docker.manager.docker.from_env") as mock_from_env:

        mock_from_env.return_value.containers.get.return_value = fake_container

        result = runner.invoke(app, ["stop", "plex"], input="y\n")

    assert result.exit_code == 0
    assert "stopped" in result.output
    fake_container.stop.assert_called_once_with()

    events = KnowledgeQueries().recent_events()

    assert events[0].event_type == "atlas.action.container_stopped"
