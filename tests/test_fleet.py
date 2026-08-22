import subprocess
from unittest.mock import MagicMock, patch

from atlas.config.models import FleetNode
from atlas.fleet import run_remote_doctor, run_remote_trends


def _node(**overrides):

    defaults = {"name": "node1", "host": "10.0.0.5", "user": "atlas", "port": 22, "identity_file": ""}

    return FleetNode(**{**defaults, **overrides})


def test_run_remote_doctor_when_ssh_not_available():

    with patch("atlas.fleet.manager.shutil.which", return_value=None):
        result = run_remote_doctor(_node())

    assert result == {"reachable": False, "error": "ssh unavailable"}


def test_run_remote_doctor_uses_batch_mode_and_connect_timeout():

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = '{"checks": [], "healthy": true}'
    fake_result.stderr = ""

    with (
        patch("atlas.fleet.manager.shutil.which", return_value="/usr/bin/ssh"),
        patch("atlas.fleet.manager.subprocess.run", return_value=fake_result) as mock_run,
    ):

        run_remote_doctor(_node())

    args = mock_run.call_args.args[0]

    assert args[0] == "/usr/bin/ssh"
    assert "-o" in args and "BatchMode=yes" in args
    assert "ConnectTimeout=5" in args
    assert "atlas@10.0.0.5" in args
    assert args[-3:] == ["atlas", "doctor", "--json"]


def test_run_remote_doctor_includes_identity_file_when_set():

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = '{"checks": [], "healthy": true}'

    with (
        patch("atlas.fleet.manager.shutil.which", return_value="/usr/bin/ssh"),
        patch("atlas.fleet.manager.subprocess.run", return_value=fake_result) as mock_run,
    ):

        run_remote_doctor(_node(identity_file="/home/atlas/.ssh/fleet_key"))

    args = mock_run.call_args.args[0]

    assert "-i" in args
    assert "/home/atlas/.ssh/fleet_key" in args


def test_run_remote_doctor_when_healthy():

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = '{"checks": [{"name": "Python", "status": true, "details": "3.12"}], "healthy": true}'

    with (
        patch("atlas.fleet.manager.shutil.which", return_value="/usr/bin/ssh"),
        patch("atlas.fleet.manager.subprocess.run", return_value=fake_result),
    ):

        result = run_remote_doctor(_node())

    assert result == {
        "reachable": True,
        "healthy": True,
        "checks": [{"name": "Python", "status": True, "details": "3.12"}]
    }


def test_run_remote_doctor_when_remote_atlas_unhealthy_but_reachable():
    """
    A remote `atlas doctor` that found something wrong exits 1 but
    still prints valid JSON - that's a real "reachable but unhealthy"
    result, not an SSH failure.
    """

    fake_result = MagicMock()
    fake_result.returncode = 1
    fake_result.stdout = '{"checks": [{"name": "Storage", "status": false, "details": "95% used"}], "healthy": false}'

    with (
        patch("atlas.fleet.manager.shutil.which", return_value="/usr/bin/ssh"),
        patch("atlas.fleet.manager.subprocess.run", return_value=fake_result),
    ):

        result = run_remote_doctor(_node())

    assert result["reachable"] is True
    assert result["healthy"] is False


def test_run_remote_doctor_when_ssh_connection_fails():

    fake_result = MagicMock()
    fake_result.returncode = 255
    fake_result.stdout = ""
    fake_result.stderr = "Permission denied (publickey)."

    with (
        patch("atlas.fleet.manager.shutil.which", return_value="/usr/bin/ssh"),
        patch("atlas.fleet.manager.subprocess.run", return_value=fake_result),
    ):

        result = run_remote_doctor(_node())

    assert result == {
        "reachable": False,
        "error": "Permission denied (publickey)."
    }


def test_run_remote_doctor_when_output_is_not_valid_json():

    fake_result = MagicMock()
    fake_result.returncode = 127
    fake_result.stdout = "bash: atlas: command not found"
    fake_result.stderr = ""

    with (
        patch("atlas.fleet.manager.shutil.which", return_value="/usr/bin/ssh"),
        patch("atlas.fleet.manager.subprocess.run", return_value=fake_result),
    ):

        result = run_remote_doctor(_node())

    assert result["reachable"] is False
    assert "could not parse" in result["error"]


def test_run_remote_doctor_when_ssh_times_out():

    with (
        patch("atlas.fleet.manager.shutil.which", return_value="/usr/bin/ssh"),
        patch(
            "atlas.fleet.manager.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ssh", 20)
        ),
    ):

        result = run_remote_doctor(_node())

    assert result["reachable"] is False


def test_run_remote_trends_uses_limit_flag():

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = '{"host": {}, "containers": {}, "guests": {}}'

    with (
        patch("atlas.fleet.manager.shutil.which", return_value="/usr/bin/ssh"),
        patch("atlas.fleet.manager.subprocess.run", return_value=fake_result) as mock_run,
    ):

        run_remote_trends(_node(), limit=5)

    args = mock_run.call_args.args[0]

    assert args[-4:] == ["trends", "--limit", "5", "--json"]


def test_run_remote_trends_when_healthy():

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = (
        '{"host": {"cpu_percent": {"latest": 30.0, "min": 10.0, "max": 30.0, '
        '"avg": 20.0, "samples": 3}}, "containers": {}, "guests": {}}'
    )

    with (
        patch("atlas.fleet.manager.shutil.which", return_value="/usr/bin/ssh"),
        patch("atlas.fleet.manager.subprocess.run", return_value=fake_result),
    ):

        result = run_remote_trends(_node())

    assert result["reachable"] is True
    assert result["host"]["cpu_percent"]["latest"] == 30.0
    assert result["containers"] == {}
    assert result["guests"] == {}


def test_run_remote_trends_when_ssh_connection_fails():

    fake_result = MagicMock()
    fake_result.returncode = 255
    fake_result.stdout = ""
    fake_result.stderr = "Connection refused"

    with (
        patch("atlas.fleet.manager.shutil.which", return_value="/usr/bin/ssh"),
        patch("atlas.fleet.manager.subprocess.run", return_value=fake_result),
    ):

        result = run_remote_trends(_node())

    assert result == {
        "reachable": False,
        "error": "Connection refused"
    }
