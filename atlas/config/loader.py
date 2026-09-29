
import os
import re
from pathlib import Path
import yaml

from atlas.config.models import AtlasConfig


CONFIG_FILE = Path("atlas.yaml")

# ${NAME} / ${NAME:-default} - lets a stack keep secrets in its .env and
# out of atlas.yaml. Only the braced form, so a literal "$" in a value
# (passwords) is never touched.
ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def expand_env(text, environ=None):

    environ = os.environ if environ is None else environ

    return ENV_REFERENCE.sub(
        lambda match: environ.get(match.group(1)) or (match.group(2) or ""),
        text
    )


def load_config():

    if not CONFIG_FILE.exists():
        return AtlasConfig()

    with open(CONFIG_FILE, "r") as file:
        data = yaml.safe_load(expand_env(file.read())) or {}

    return AtlasConfig(**data)
