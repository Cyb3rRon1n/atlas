from unittest.mock import MagicMock, patch

from atlas.docker import collect_containers


def test_collect_containers_when_daemon_unavailable():
    """
    GitHub-hosted runners have a live Docker daemon, so this mocks the
    "unavailable" path explicitly rather than relying on the ambient
    environment lacking Docker.
    """

    with patch(
        "atlas.docker.manager.docker.from_env",
        side_effect=RuntimeError("no docker socket")
    ):

        result = collect_containers()

    assert result == {"available": False, "containers": []}


def test_collect_containers_when_available():

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.image.tags = ["plexinc/pms-docker:latest"]
    fake_container.status = "running"
    fake_container.short_id = "abc123"

    fake_client = MagicMock()
    fake_client.containers.list.return_value = [fake_container]

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = collect_containers()

    assert result["available"] is True
    assert result["containers"] == [
        {
            "name": "plex",
            "image": ["plexinc/pms-docker:latest"],
            "status": "running",
            "id": "abc123",
        }
    ]

    fake_client.containers.list.assert_called_once_with(all=True)
