import json

import docker


def get_client():

    try:
        return docker.from_env()

    except Exception:
        return None



def collect_containers():

    client = get_client()

    if not client:
        return {
            "available": False,
            "containers": []
        }


    containers = []

    for container in client.containers.list(
        all=True
    ):

        containers.append(
            {
                "name": container.name,
                "image": container.image.tags,
                "status": container.status,
                "id": container.short_id,
            }
        )


    return {
        "available": True,
        "containers": containers
    }


def get_container_info(name):

    client = get_client()

    if not client:
        return {
            "found": False,
            "error": "Docker unavailable"
        }

    try:
        container = client.containers.get(name)

    except docker.errors.NotFound:
        return {
            "found": False,
            "error": f"No container named '{name}' found"
        }

    host_config = container.attrs.get("HostConfig", {})

    # `docker run --cpus` (the common path) sets NanoCpus, not
    # CpuPeriod/CpuQuota - confirmed against a real container: `docker
    # inspect` shows CpuPeriod=0/CpuQuota=0 even though a real limit is
    # enforced (cAdvisor reads the actual kernel cgroup values and
    # reports the equivalent CpuQuota/CpuPeriod correctly - it's only
    # this HostConfig field in `docker inspect` that doesn't reflect
    # NanoCpus back into the legacy fields). CpuPeriod/CpuQuota are the
    # fallback for a limit set that way directly instead.
    nano_cpus = host_config.get("NanoCpus") or 0
    cpu_period = host_config.get("CpuPeriod") or 0
    cpu_quota = host_config.get("CpuQuota") or 0
    memory = host_config.get("Memory") or 0

    if nano_cpus:
        cpu_limit_cores = nano_cpus / 1_000_000_000

    elif cpu_quota and cpu_period:
        cpu_limit_cores = cpu_quota / cpu_period

    else:
        cpu_limit_cores = None

    return {
        "found": True,
        "name": container.name,
        "image": container.image.tags,
        "status": container.status,
        "cpu_limit_cores": cpu_limit_cores,
        "memory_limit_bytes": memory if memory else None,
    }


def restart_container(name):

    client = get_client()

    if not client:
        return {
            "success": False,
            "error": "Docker unavailable"
        }

    try:
        container = client.containers.get(name)

    except docker.errors.NotFound:
        return {
            "success": False,
            "error": f"No container named '{name}' found"
        }

    previous_status = container.status

    try:
        container.restart()

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }

    return {
        "success": True,
        "previous_status": previous_status
    }


def resize_container(name, cpus=None, mem_limit=None):
    """
    Live-update a container's CPU/memory limit - no restart. Only
    includes the fields actually given, so a cpus-only resize doesn't
    touch memory at all, and vice versa.

    Deliberately does NOT use docker-py's container.update() /
    cpu_period+cpu_quota - verified against a real container created
    the standard way (`docker run --cpus=0.5`, which is what `docker
    ps`/`docker run` actually do): Docker sets NanoCPUs, not
    CpuPeriod/CpuQuota, and the daemon then rejects a period/quota
    update on that same container with a real 409 Conflict
    ("CPU Period cannot be updated as NanoCPUs has already been
    set"). docker-py's container.update() wrapper has no NanoCPUs
    parameter at all (confirmed against the installed docker-py 7.2.0
    - its update_container() signature simply doesn't accept it), so
    this posts the raw Docker Engine API request directly instead,
    reusing docker-py's own session/transport (client.api, a
    requests.Session with the Docker socket adapter already
    registered) rather than adding a new HTTP dependency or shelling
    out to the docker CLI. docker.utils.parse_bytes() (the same public
    helper container.update() uses internally) parses a human memory
    string ("512m", "1g") into raw bytes for the request body.
    """

    client = get_client()

    if not client:
        return {
            "success": False,
            "error": "Docker unavailable"
        }

    try:
        container = client.containers.get(name)

    except docker.errors.NotFound:
        return {
            "success": False,
            "error": f"No container named '{name}' found"
        }

    body = {}

    if cpus is not None:
        body["NanoCPUs"] = int(cpus * 1_000_000_000)

    if mem_limit is not None:
        body["Memory"] = docker.utils.parse_bytes(mem_limit)

    try:
        response = client.api.post(
            f"{client.api.base_url}/containers/{container.id}/update",
            data=json.dumps(body),
            headers={"Content-Type": "application/json"}
        )

        response.raise_for_status()

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }

    return {
        "success": True
    }


def stop_container(name):

    client = get_client()

    if not client:
        return {
            "success": False,
            "error": "Docker unavailable"
        }

    try:
        container = client.containers.get(name)

    except docker.errors.NotFound:
        return {
            "success": False,
            "error": f"No container named '{name}' found"
        }

    previous_status = container.status

    try:
        container.stop()

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }

    return {
        "success": True,
        "previous_status": previous_status
    }
