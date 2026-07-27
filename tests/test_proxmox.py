from unittest.mock import MagicMock, patch

from atlas.proxmox.client import connect
from atlas.proxmox.discovery import discover_nodes, discover_resources


def test_connect_returns_client_on_success():

    fake_client = MagicMock()

    with patch(
        "atlas.proxmox.client.ProxmoxAPI",
        return_value=fake_client
    ) as mock_api:

        client = connect(
            "proxmox.local",
            "root@pam",
            "hunter2"
        )

    assert client is fake_client
    mock_api.assert_called_once_with(
        "proxmox.local",
        user="root@pam",
        password="hunter2",
        verify_ssl=False
    )


def test_connect_returns_none_on_failure():

    with patch(
        "atlas.proxmox.client.ProxmoxAPI",
        side_effect=RuntimeError("connection refused")
    ):

        client = connect(
            "proxmox.local",
            "root@pam",
            "hunter2"
        )

    assert client is None


def test_connect_prefers_token_auth_when_configured():

    fake_client = MagicMock()

    with patch(
        "atlas.proxmox.client.ProxmoxAPI",
        return_value=fake_client
    ) as mock_api:

        client = connect(
            "proxmox.local",
            "atlas@pve",
            password="unused",
            token_name="atlas-token",
            token_value="secret-value"
        )

    assert client is fake_client
    mock_api.assert_called_once_with(
        "proxmox.local",
        user="atlas@pve",
        token_name="atlas-token",
        token_value="secret-value",
        verify_ssl=False
    )


def test_discover_nodes_returns_empty_list_when_no_client():

    assert discover_nodes(None) == []


def test_discover_nodes_maps_node_fields():

    fake_client = MagicMock()
    fake_client.nodes.get.return_value = [
        {"node": "pve1", "status": "online"},
        {"node": "pve2", "status": "offline"},
    ]

    nodes = discover_nodes(fake_client)

    assert nodes == [
        {"name": "pve1", "status": "online"},
        {"name": "pve2", "status": "offline"},
    ]


def test_discover_resources_returns_empty_list_when_no_client():

    assert discover_resources(None) == []


def test_discover_resources_maps_vm_and_container_fields():

    fake_client = MagicMock()
    fake_client.cluster.resources.get.return_value = [
        {
            "vmid": 100,
            "name": "plex-vm",
            "node": "pve1",
            "type": "qemu",
            "status": "running",
            "cpu": 0.05,
            "maxcpu": 4,
            "mem": 1073741824,
            "maxmem": 4294967296,
            "disk": 0,
            "maxdisk": 34359738368,
            "uptime": 12345,
        },
        {
            "vmid": 101,
            "name": "pihole-lxc",
            "node": "pve1",
            "type": "lxc",
            "status": "stopped",
        },
    ]

    guests = discover_resources(fake_client)

    assert guests[0] == {
        "vmid": 100,
        "name": "plex-vm",
        "node": "pve1",
        "type": "qemu",
        "status": "running",
        "cpu": 0.05,
        "maxcpu": 4,
        "mem": 1073741824,
        "maxmem": 4294967296,
        "disk": 0,
        "maxdisk": 34359738368,
        "uptime": 12345,
    }

    assert guests[1]["vmid"] == 101
    assert guests[1]["type"] == "lxc"
    assert guests[1]["status"] == "stopped"
    assert guests[1]["cpu"] is None

    fake_client.cluster.resources.get.assert_called_once_with(type="vm")
