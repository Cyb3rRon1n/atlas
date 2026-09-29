
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


def _expand_values(value):
    """
    Expand ${...} inside string values *after* YAML parsing - expanding the
    raw text first turned `api_key: ${UNSET}` into `api_key:` (YAML null,
    rejected by the str field) and crashed a fresh stack with no key yet.
    """

    if isinstance(value, str):
        return expand_env(value)

    if isinstance(value, dict):
        return {key: _expand_values(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_expand_values(item) for item in value]

    return value


def load_config():

    if not CONFIG_FILE.exists():
        return AtlasConfig()

    with open(CONFIG_FILE, "r") as file:
        data = _expand_values(yaml.safe_load(file) or {})

    return AtlasConfig(**data)
