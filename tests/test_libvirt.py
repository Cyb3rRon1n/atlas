import subprocess
from unittest.mock import MagicMock, patch

from atlas.config.models import FleetNode
from atlas.libvirt import collect_guests, get_guest_info, resize_guest, restart_guest, stop_guest


def _node(**overrides):

    defaults = {"name": "node1", "host": "10.0.0.5", "user": "atlas", "port": 22, "identity_file": ""}

    return FleetNode(**{**defaults, **overrides})


def test_collect_guests_when_virsh_not_available():

    with patch("atlas.libvirt.manager.shutil.which", return_value=None):
        result = collect_guests()

    assert result == {"available": False, "guests": []}


def test_collect_guests_when_list_command_fails():

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch(
            "atlas.libvirt.manager.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "virsh")
        ),
    ):

        result = collect_guests()

    assert result == {"available": False, "guests": []}


def test_collect_guests_when_available():

    def fake_run(cmd, **kwargs):

        result = MagicMock()

        if cmd[1:] == ["list", "--all", "--name"]:
            result.stdout = "vm1\n\n"
        elif cmd[1:] == ["domstate", "vm1"]:
            result.stdout = "running\n"
        elif cmd[1:] == ["domuuid", "vm1"]:
            result.stdout = "abc-123\n"
        else:
            raise AssertionError(f"unexpected virsh call: {cmd}")

        return result

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", side_effect=fake_run),
    ):

        result = collect_guests()

    assert result == {
        "available": True,
        "guests": [{"name": "vm1", "uuid": "abc-123", "state": "running"}],
    }


def test_collect_guests_when_guest_state_lookup_fails():
    """
    A per-guest domstate/domuuid failure shouldn't drop the whole scan
    - the guest still shows up, just with unknown state.
    """

    def fake_run(cmd, **kwargs):

        result = MagicMock()

        if cmd[1:] == ["list", "--all", "--name"]:
            result.stdout = "vm1\n"
            return result

        raise subprocess.CalledProcessError(1, "virsh")

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", side_effect=fake_run),
    ):

        result = collect_guests()

    assert result["guests"] == [{"name": "vm1", "uuid": "", "state": "unknown"}]


def test_get_guest_info_when_virsh_not_available():

    with patch("atlas.libvirt.manager.shutil.which", return_value=None):
        result = get_guest_info("vm1")

    assert result == {"found": False, "error": "libvirt/virsh unavailable"}


def test_get_guest_info_when_guest_not_found():

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch(
            "atlas.libvirt.manager.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "virsh")
        ),
    ):

        result = get_guest_info("nope")

    assert result == {
        "found": False,
        "error": "No libvirt guest named 'nope' found"
    }


def test_get_guest_info_when_found():

    fake_result = MagicMock()
    fake_result.stdout = "running\n"

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", return_value=fake_result),
    ):

        result = get_guest_info("vm1")

    assert result == {"found": True, "name": "vm1", "state": "running"}


def test_restart_guest_when_virsh_not_available():

    with patch("atlas.libvirt.manager.shutil.which", return_value=None):
        result = restart_guest("vm1")

    assert result == {"success": False, "error": "libvirt/virsh unavailable"}


def test_restart_guest_when_successful():

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", return_value=MagicMock()),
    ):

        result = restart_guest("vm1")

    assert result == {"success": True}


def test_restart_guest_when_command_fails_uses_stderr():

    error = subprocess.CalledProcessError(1, "virsh")
    error.stderr = "error: failed to get domain 'vm1'\n"

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", side_effect=error),
    ):

        result = restart_guest("vm1")

    assert result == {
        "success": False,
        "error": "error: failed to get domain 'vm1'"
    }


def test_restart_guest_when_command_times_out():

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch(
            "atlas.libvirt.manager.subprocess.run",
            side_effect=subprocess.TimeoutExpired("virsh", 5)
        ),
    ):

        result = restart_guest("vm1")

    assert result["success"] is False


def test_stop_guest_when_virsh_not_available():

    with patch("atlas.libvirt.manager.shutil.which", return_value=None):
        result = stop_guest("vm1")

    assert result == {"success": False, "error": "libvirt/virsh unavailable"}


def test_stop_guest_sends_shutdown_not_destroy():

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", return_value=MagicMock()) as mock_run,
    ):

        result = stop_guest("vm1")

    assert result == {"success": True}
    mock_run.assert_called_once_with(
        ["/usr/bin/virsh", "shutdown", "vm1"],
        capture_output=True, text=True, timeout=5, check=True
    )


def test_resize_guest_when_virsh_not_available():

    with patch("atlas.libvirt.manager.shutil.which", return_value=None):
        result = resize_guest("vm1", vcpus=2)

    assert result == {"success": False, "error": "libvirt/virsh unavailable"}


def test_resize_guest_sets_vcpus_and_memory():

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", return_value=MagicMock()) as mock_run,
    ):

        result = resize_guest("vm1", vcpus=2, memory="512MiB")

    assert result == {"success": True}
    assert mock_run.call_args_list[0].args[0] == [
        "/usr/bin/virsh", "setvcpus", "vm1", "2", "--config"
    ]
    assert mock_run.call_args_list[1].args[0] == [
        "/usr/bin/virsh", "setmem", "vm1", "512MiB", "--config"
    ]


def test_resize_guest_vcpus_only_does_not_call_setmem():

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", return_value=MagicMock()) as mock_run,
    ):

        resize_guest("vm1", vcpus=2)

    assert mock_run.call_count == 1
    assert mock_run.call_args.args[0][1] == "setvcpus"


def test_resize_guest_stops_after_first_failure():
    """
    A failed setvcpus shouldn't still attempt setmem - matches
    _run_command's fail-fast shape used everywhere else.
    """

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch(
            "atlas.libvirt.manager.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "virsh")
        ) as mock_run,
    ):

        result = resize_guest("vm1", vcpus=2, memory="512MiB")

    assert result["success"] is False
    assert mock_run.call_count == 1


def test_restart_guest_with_node_uses_connect_uri():

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", return_value=MagicMock()) as mock_run,
    ):

        restart_guest("vm1", node=_node())

    assert mock_run.call_args.args[0] == [
        "/usr/bin/virsh", "-c", "qemu+ssh://atlas@10.0.0.5/system", "reboot", "vm1"
    ]


def test_get_guest_info_with_node_uses_connect_uri():

    fake_result = MagicMock()
    fake_result.stdout = "running\n"

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", return_value=fake_result) as mock_run,
    ):

        get_guest_info("vm1", node=_node())

    assert mock_run.call_args.args[0] == [
        "/usr/bin/virsh", "-c", "qemu+ssh://atlas@10.0.0.5/system", "domstate", "vm1"
    ]


def test_resize_guest_with_node_uses_connect_uri_on_both_calls():

    with (
        patch("atlas.libvirt.manager.shutil.which", return_value="/usr/bin/virsh"),
        patch("atlas.libvirt.manager.subprocess.run", return_value=MagicMock()) as mock_run,
    ):

        resize_guest("vm1", vcpus=2, memory="512MiB", node=_node())

    assert mock_run.call_args_list[0].args[0] == [
        "/usr/bin/virsh", "-c", "qemu+ssh://atlas@10.0.0.5/system",
        "setvcpus", "vm1", "2", "--config"
    ]
    assert mock_run.call_args_list[1].args[0] == [
        "/usr/bin/virsh", "-c", "qemu+ssh://atlas@10.0.0.5/system",
        "setmem", "vm1", "512MiB", "--config"
    ]
