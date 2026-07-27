from unittest.mock import MagicMock, patch

import docker.errors

from atlas.docker import collect_containers, get_container_info, restart_container


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


def test_get_container_info_when_daemon_unavailable():

    with patch(
        "atlas.docker.manager.docker.from_env",
        side_effect=RuntimeError("no docker socket")
    ):

        result = get_container_info("plex")

    assert result == {"found": False, "error": "Docker unavailable"}


def test_get_container_info_when_not_found():

    fake_client = MagicMock()
    fake_client.containers.get.side_effect = docker.errors.NotFound("not found")

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = get_container_info("missing")

    assert result == {
        "found": False,
        "error": "No container named 'missing' found"
    }


def test_get_container_info_when_found():

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.image.tags = ["plexinc/pms-docker:latest"]
    fake_container.status = "exited"

    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = get_container_info("plex")

    assert result == {
        "found": True,
        "name": "plex",
        "image": ["plexinc/pms-docker:latest"],
        "status": "exited",
    }

    fake_client.containers.get.assert_called_once_with("plex")


def test_restart_container_when_daemon_unavailable():

    with patch(
        "atlas.docker.manager.docker.from_env",
        side_effect=RuntimeError("no docker socket")
    ):

        result = restart_container("plex")

    assert result == {"success": False, "error": "Docker unavailable"}


def test_restart_container_when_not_found():

    fake_client = MagicMock()
    fake_client.containers.get.side_effect = docker.errors.NotFound("not found")

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = restart_container("missing")

    assert result == {
        "success": False,
        "error": "No container named 'missing' found"
    }


def test_restart_container_when_restart_raises():

    fake_container = MagicMock()
    fake_container.status = "running"
    fake_container.restart.side_effect = RuntimeError("daemon exploded")

    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = restart_container("plex")

    assert result == {"success": False, "error": "daemon exploded"}


def test_restart_container_when_successful():

    fake_container = MagicMock()
    fake_container.status = "exited"

    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = restart_container("plex")

    assert result == {"success": True, "previous_status": "exited"}

    fake_container.restart.assert_called_once_with()
