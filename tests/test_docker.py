import json
from unittest.mock import MagicMock, patch

import docker.errors

from atlas.docker import (
    collect_containers,
    get_container_info,
    get_container_logs,
    resize_container,
    restart_container,
    stop_container,
)


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
    fake_container.attrs = {"HostConfig": {}}

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
        "cpu_limit_cores": None,
        "memory_limit_bytes": None,
    }

    fake_client.containers.get.assert_called_once_with("plex")


def test_get_container_info_reports_configured_limits():

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.image.tags = ["plexinc/pms-docker:latest"]
    fake_container.status = "running"
    fake_container.attrs = {
        "HostConfig": {
            "CpuPeriod": 100000,
            "CpuQuota": 50000,
            "Memory": 268435456,
        }
    }

    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = get_container_info("plex")

    assert result["cpu_limit_cores"] == 0.5
    assert result["memory_limit_bytes"] == 268435456


def test_get_container_info_reads_nanocpus_for_docker_run_cpus_flag():
    """
    Verified against a real container: `docker run --cpus=0.5` sets
    NanoCpus, not CpuPeriod/CpuQuota - `docker inspect` shows those
    as 0 even though a real limit is enforced. NanoCpus has to be
    checked first, or the common case (`--cpus` at container-create
    time) would incorrectly report "unlimited".
    """

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.image.tags = ["plexinc/pms-docker:latest"]
    fake_container.status = "running"
    fake_container.attrs = {
        "HostConfig": {
            "NanoCpus": 500000000,
            "CpuPeriod": 0,
            "CpuQuota": 0,
            "Memory": 268435456,
        }
    }

    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = get_container_info("plex")

    assert result["cpu_limit_cores"] == 0.5


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


def test_stop_container_when_daemon_unavailable():

    with patch(
        "atlas.docker.manager.docker.from_env",
        side_effect=RuntimeError("no docker socket")
    ):

        result = stop_container("plex")

    assert result == {"success": False, "error": "Docker unavailable"}


def test_stop_container_when_not_found():

    fake_client = MagicMock()
    fake_client.containers.get.side_effect = docker.errors.NotFound("not found")

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = stop_container("missing")

    assert result == {
        "success": False,
        "error": "No container named 'missing' found"
    }


def test_stop_container_when_stop_raises():

    fake_container = MagicMock()
    fake_container.status = "running"
    fake_container.stop.side_effect = RuntimeError("daemon exploded")

    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = stop_container("plex")

    assert result == {"success": False, "error": "daemon exploded"}


def test_stop_container_when_successful():

    fake_container = MagicMock()
    fake_container.status = "running"

    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = stop_container("plex")

    assert result == {"success": True, "previous_status": "running"}

    fake_container.stop.assert_called_once_with()


def _fake_docker_client_for_resize():
    """
    resize_container() posts the raw Docker Engine API request via
    client.api (docker-py's requests.Session subclass) rather than
    container.update() - see resize_container()'s docstring for why.
    api.base_url and api.post are the two pieces that call needs.
    """

    fake_container = MagicMock()
    fake_container.id = "abc123"

    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container
    fake_client.api.base_url = "http+docker://localhost"

    fake_response = MagicMock()
    fake_client.api.post.return_value = fake_response

    return fake_client, fake_container, fake_response


def test_resize_container_when_daemon_unavailable():

    with patch(
        "atlas.docker.manager.docker.from_env",
        side_effect=RuntimeError("no docker socket")
    ):

        result = resize_container("plex", cpus=0.5)

    assert result == {"success": False, "error": "Docker unavailable"}


def test_resize_container_when_not_found():

    fake_client = MagicMock()
    fake_client.containers.get.side_effect = docker.errors.NotFound("not found")

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = resize_container("missing", mem_limit="512m")

    assert result == {
        "success": False,
        "error": "No container named 'missing' found"
    }


def test_resize_container_when_update_raises():

    fake_client, fake_container, fake_response = _fake_docker_client_for_resize()
    fake_response.raise_for_status.side_effect = RuntimeError("daemon exploded")

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = resize_container("plex", mem_limit="512m")

    assert result == {"success": False, "error": "daemon exploded"}


def test_resize_container_posts_nanocpus_for_cpus():
    """
    Verified against a real container created the standard way
    (`docker run --cpus=0.5`): Docker sets NanoCPUs, not
    CpuPeriod/CpuQuota, and rejects a period/quota update on that
    same container with a real 409 conflict. NanoCPUs is nanocores -
    0.5 cores -> 500000000.
    """

    fake_client, fake_container, _ = _fake_docker_client_for_resize()

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = resize_container("plex", cpus=0.5)

    assert result == {"success": True}

    args, kwargs = fake_client.api.post.call_args
    assert args[0] == "http+docker://localhost/containers/abc123/update"
    assert json.loads(kwargs["data"]) == {"NanoCPUs": 500000000}


def test_resize_container_with_memory_only_does_not_touch_cpu():

    fake_client, fake_container, _ = _fake_docker_client_for_resize()

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = resize_container("plex", mem_limit="1g")

    assert result == {"success": True}

    _, kwargs = fake_client.api.post.call_args
    assert json.loads(kwargs["data"]) == {"Memory": 1073741824}


def test_resize_container_with_both_cpus_and_memory():

    fake_client, fake_container, _ = _fake_docker_client_for_resize()

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = resize_container("plex", cpus=1.0, mem_limit="512m")

    assert result == {"success": True}

    _, kwargs = fake_client.api.post.call_args
    assert json.loads(kwargs["data"]) == {
        "NanoCPUs": 1000000000, "Memory": 536870912
    }


def test_get_container_logs_when_daemon_unavailable():

    with patch(
        "atlas.docker.manager.docker.from_env",
        side_effect=RuntimeError("no docker socket")
    ):

        result = get_container_logs("plex")

    assert result == {"found": False, "error": "Docker unavailable"}


def test_get_container_logs_when_not_found():

    fake_client = MagicMock()
    fake_client.containers.get.side_effect = docker.errors.NotFound("not found")

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = get_container_logs("missing")

    assert result == {
        "found": False,
        "error": "No container named 'missing' found"
    }


def test_get_container_logs_when_logs_raises():

    fake_container = MagicMock()
    fake_container.logs.side_effect = RuntimeError("daemon exploded")

    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = get_container_logs("plex")

    assert result == {"found": False, "error": "daemon exploded"}


def test_get_container_logs_when_successful():

    fake_container = MagicMock()
    fake_container.name = "plex"
    fake_container.logs.return_value = b"line one\nline two\n"

    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container

    with patch(
        "atlas.docker.manager.docker.from_env",
        return_value=fake_client
    ):

        result = get_container_logs("plex", tail=50)

    assert result == {
        "found": True,
        "name": "plex",
        "logs": "line one\nline two\n"
    }

    fake_container.logs.assert_called_once_with(tail=50, timestamps=False)
