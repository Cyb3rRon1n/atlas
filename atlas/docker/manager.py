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
