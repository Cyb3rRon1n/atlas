from datetime import datetime
from pathlib import Path

import yaml

from atlas.config.loader import CONFIG_FILE
from atlas.config.models import AtlasConfig


def write_config(config: AtlasConfig, path: Path = CONFIG_FILE):

    with open(path, "w") as file:

        yaml.safe_dump(
            config.model_dump(),
            file,
            sort_keys=False
        )


def write_setup_log(lines: list[str], directory: Path = Path("logs")) -> Path:

    directory.mkdir(
        parents=True,
        exist_ok=True
    )

    log_path = directory / (
        "atlas-init-"
        f"{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.log"
    )

    with open(log_path, "w") as file:

        file.write(
            "\n".join(lines) + "\n"
        )

    return log_path
