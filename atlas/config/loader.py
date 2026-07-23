from pathlib import Path
import yaml

from atlas.config.models import AtlasConfig


CONFIG_FILE = Path("atlas.yaml")


def load_config():

    if not CONFIG_FILE.exists():
        return AtlasConfig()

    with open(CONFIG_FILE, "r") as file:
        data = yaml.safe_load(file)

    return AtlasConfig(**data)

