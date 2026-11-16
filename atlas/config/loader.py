
import os
import re
import yaml

from atlas.config import local
from atlas.config.models import AtlasConfig


CONFIG_FILE = local.CONFIG_FILE

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
    """atlas.yaml, with settings saved from the web Setup page filling in what it leaves out (atlas.config.local)."""

    local.apply_secrets()
    user = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as file:
            user = yaml.safe_load(file) or {}

    return AtlasConfig(**_expand_values(local.layered(user, local.read_settings())))
