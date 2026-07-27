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

    return {
        "found": True,
        "name": container.name,
        "image": container.image.tags,
        "status": container.status,
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
