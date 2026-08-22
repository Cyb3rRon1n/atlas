import subprocess
from unittest.mock import MagicMock, patch

from atlas.libvirt import collect_guests


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
