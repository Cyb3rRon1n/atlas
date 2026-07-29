from unittest.mock import MagicMock, patch

from atlas.proxmox.manager import get_guest_info, resize_guest, restart_guest, stop_guest


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


def test_stop_guest_success_for_qemu():

    fake_client = MagicMock()

    result = stop_guest(fake_client, "pve1", 100, "qemu")

    assert result == {"success": True}
    fake_client.nodes.assert_called_once_with("pve1")
    fake_client.nodes.return_value.qemu.assert_called_once_with(100)
    (
        fake_client.nodes.return_value.qemu.return_value
        .status.shutdown.post.assert_called_once_with()
    )


def test_stop_guest_success_for_lxc():

    fake_client = MagicMock()

    result = stop_guest(fake_client, "pve1", 101, "lxc")

    assert result == {"success": True}
    fake_client.nodes.assert_called_once_with("pve1")
    fake_client.nodes.return_value.lxc.assert_called_once_with(101)
    (
        fake_client.nodes.return_value.lxc.return_value
        .status.shutdown.post.assert_called_once_with()
    )


def test_stop_guest_returns_error_dict_instead_of_raising():

    fake_client = MagicMock()

    fake_client.nodes.return_value.lxc.return_value.status.shutdown.post.side_effect = (
        RuntimeError("guest is locked")
    )

    result = stop_guest(fake_client, "pve1", 101, "lxc")

    assert result == {"success": False, "error": "guest is locked"}


def test_resize_guest_sends_cpulimit_for_qemu():

    fake_client = MagicMock()

    result = resize_guest(fake_client, "pve1", 100, "qemu", cpus=1.5)

    assert result == {"success": True}
    fake_client.nodes.assert_called_once_with("pve1")
    fake_client.nodes.return_value.qemu.assert_called_once_with(100)
    (
        fake_client.nodes.return_value.qemu.return_value
        .config.put.assert_called_once_with(cpulimit=1.5)
    )


def test_resize_guest_converts_memory_string_to_mb_for_lxc():

    fake_client = MagicMock()

    result = resize_guest(fake_client, "pve1", 101, "lxc", memory="512m")

    assert result == {"success": True}
    (
        fake_client.nodes.return_value.lxc.return_value
        .config.put.assert_called_once_with(memory=512)
    )


def test_resize_guest_sends_both_cpus_and_memory():

    fake_client = MagicMock()

    result = resize_guest(fake_client, "pve1", 100, "qemu", cpus=2.0, memory="1g")

    assert result == {"success": True}
    (
        fake_client.nodes.return_value.qemu.return_value
        .config.put.assert_called_once_with(cpulimit=2.0, memory=1024)
    )


def test_resize_guest_returns_error_dict_instead_of_raising():

    fake_client = MagicMock()

    fake_client.nodes.return_value.qemu.return_value.config.put.side_effect = (
        RuntimeError("guest is locked")
    )

    result = resize_guest(fake_client, "pve1", 100, "qemu", cpus=1.0)

    assert result == {"success": False, "error": "guest is locked"}
