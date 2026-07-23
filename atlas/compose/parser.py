from pathlib import Path
import yaml

from atlas.compose.models import (
    ComposeProject,
    ComposeService,
)


def parse_compose_file(path):

    file = Path(path)

    if not file.exists():
        return None


    with open(file) as f:
        data = yaml.safe_load(f)


    services = []


    for name, service in data.get(
        "services",
        {}
    ).items():

        services.append(
            ComposeService(
                name=name,
                image=service.get(
                    "image"
                ),
                ports=service.get(
                    "ports",
                    []
                ),
                volumes=service.get(
                    "volumes",
                    []
                ),
            )
        )


    return ComposeProject(
        name=file.parent.name,
        services=services,
    )
