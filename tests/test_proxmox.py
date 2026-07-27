from unittest.mock import MagicMock, patch

from atlas.proxmox.client import connect
from atlas.proxmox.discovery import discover_nodes


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
