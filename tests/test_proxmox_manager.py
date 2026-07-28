from unittest.mock import MagicMock, patch

from atlas.proxmox.manager import get_guest_info, restart_guest


def test_get_guest_info_found():

    fake_client = MagicMock()

    with patch(
        "atlas.proxmox.manager.discover_resources",
        return_value=[
            {
                "vmid": 100, "name": "plex", "node": "pve1", "type": "qemu",
                "status": "running", "cpu": 0.1, "maxcpu": 4, "mem": 100,
                "maxmem": 1000, "disk": 0, "maxdisk": 0, "uptime": 10
            }
        ]
    ):

        info = get_guest_info(fake_client, 100)

    assert info["found"] is True
    assert info["name"] == "plex"
    assert info["node"] == "pve1"
    assert info["type"] == "qemu"


def test_get_guest_info_not_found():

    fake_client = MagicMock()

    with patch(
        "atlas.proxmox.manager.discover_resources",
        return_value=[]
    ):

        info = get_guest_info(fake_client, 999)

    assert info["found"] is False
    assert "999" in info["error"]


def test_restart_guest_success_for_qemu():

    fake_client = MagicMock()

    result = restart_guest(fake_client, "pve1", 100, "qemu")

    assert result == {"success": True}
    fake_client.nodes.assert_called_once_with("pve1")
    fake_client.nodes.return_value.qemu.assert_called_once_with(100)
    (
        fake_client.nodes.return_value.qemu.return_value
        .status.reboot.post.assert_called_once_with()
    )


def test_restart_guest_success_for_lxc():

    fake_client = MagicMock()

    result = restart_guest(fake_client, "pve1", 101, "lxc")

    assert result == {"success": True}
    fake_client.nodes.assert_called_once_with("pve1")
    fake_client.nodes.return_value.lxc.assert_called_once_with(101)
    (
        fake_client.nodes.return_value.lxc.return_value
        .status.reboot.post.assert_called_once_with()
    )


def test_restart_guest_returns_error_dict_instead_of_raising():

    fake_client = MagicMock()

    fake_client.nodes.return_value.qemu.return_value.status.reboot.post.side_effect = (
        RuntimeError("guest is locked")
    )

    result = restart_guest(fake_client, "pve1", 100, "qemu")

    assert result == {"success": False, "error": "guest is locked"}
