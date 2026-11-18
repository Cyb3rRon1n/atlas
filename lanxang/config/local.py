"""
Settings saved from the web Setup page, kept beside the database (inventory/, the Docker data volume).

The config file stays the user's file: it is never rewritten, and any value it sets wins over a web-saved one.
settings.yaml only fills in what the config file leaves out. Secrets live apart in secrets.json (mode 600), keyed
by the environment variable names Lanxang already reads (LANXANG_UNIFI_PASS, LANXANG_SNMP_<NAME>_AUTH, ...).
load_config() puts them into the environment unless the real environment (.env) already sets them, so
settings.yaml can reference them as ${NAME} and secret values never appear in a settings file or a page.
"""

import json
import os
import re
from pathlib import Path

import yaml

from lanxang.config.env import NEW as NEW_PREFIX, OLD as OLD_PREFIX, mirror

SETTINGS_FILE = Path("inventory/settings.yaml")
SECRETS_FILE = Path("inventory/secrets.json")
NEW_CONFIG, OLD_CONFIG = Path("lanxang.yaml"), Path("atlas.yaml")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")

_APPLIED = set()     # environment keys this process set from secrets.json (so a later change can replace them)


def config_file():
    """lanxang.yaml, or an existing install's atlas.yaml when only that exists (read until 1.2)."""

    return OLD_CONFIG if OLD_CONFIG.is_file() and not NEW_CONFIG.is_file() else NEW_CONFIG


def config_name():
    """The config file's name for messages: lanxang.yaml, or atlas.yaml on an install that still has only that."""

    return config_file().name


def _read_yaml(path):

    try:
        data = yaml.safe_load(path.read_text()) if path.exists() else {}
    except (OSError, yaml.YAMLError):
        return {}

    return data if isinstance(data, dict) else {}


def _write(path, text, mode):
    """Atomic write: a crash mid-save never leaves half a file, and secrets are never briefly world-readable."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as file:
        file.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _merge(base, patch):
    """patch into base; None removes a key; dicts merge, anything else replaces."""

    out = dict(base)
    for key, value in patch.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, dict):
            out[key] = _merge(out[key] if isinstance(out.get(key), dict) else {}, value)
        else:
            out[key] = value

    return {key: value for key, value in out.items() if value != {}}


def layered(user, web):
    """The effective settings: web values only where the user's config file has none."""

    out = dict(web)
    for key, value in user.items():
        out[key] = layered(value, web[key]) if isinstance(value, dict) and isinstance(web.get(key), dict) else value

    return out


def read_settings():

    return _read_yaml(SETTINGS_FILE)


def save_settings(patch):

    _write(SETTINGS_FILE, yaml.safe_dump(_merge(read_settings(), patch), sort_keys=False), 0o644)


def locked(path):
    """True when the config file sets this setting (a tuple of keys), so the Setup page shows it read-only."""

    node = _read_yaml(config_file())
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]

    return True


def _read_secrets():

    try:
        data = json.loads(SECRETS_FILE.read_text()) if SECRETS_FILE.exists() else {}
    except (OSError, ValueError):
        return {}

    return {k: v for k, v in data.items() if isinstance(v, str)} if isinstance(data, dict) else {}


def _counterpart(name):
    """The same setting under the other prefix (LANXANG_X <-> ATLAS_X); None for any other name."""

    if name.startswith(NEW_PREFIX):
        return OLD_PREFIX + name[len(NEW_PREFIX):]
    if name.startswith(OLD_PREFIX):
        return NEW_PREFIX + name[len(OLD_PREFIX):]


def _normal(name):

    return NEW_PREFIX + name[len(OLD_PREFIX):] if name.startswith(OLD_PREFIX) else name


def secret_names():
    """Which secrets are saved - never their values. An old install's ATLAS_ keys are listed as LANXANG_."""

    return {_normal(name) for name in _read_secrets()}


def save_secrets(values):
    """{ENV_NAME: value}; None or "" removes one (under either prefix, so an old ATLAS_ key never lingers)."""

    for name in values:
        if not ENV_NAME.match(name):
            raise ValueError(f"not an environment variable name: {name!r}")
    current = _read_secrets()
    for name, value in values.items():
        current.pop(_counterpart(name), None)
        if value:
            current[name] = value
        else:
            current.pop(name, None)
    _write(SECRETS_FILE, json.dumps(current, indent=1), 0o600)


def _drop_copy(environ, name, was):
    """Remove the mirrored copy of name - only while it still holds the value mirror() gave it."""

    other = _counterpart(name)
    if other and environ.get(other) == was:
        environ.pop(other, None)


def apply_secrets(environ=None):
    """Put saved secrets into the environment; a variable the real environment sets always wins."""

    environ = os.environ if environ is None else environ
    stored = _read_secrets()
    for name in list(_APPLIED):
        if name not in stored:
            was = environ.pop(name, None)
            _drop_copy(environ, name, was)      # the mirrored copy, or it would bring the secret back
            _APPLIED.discard(name)
    for name, value in stored.items():
        if name in _APPLIED or not environ.get(name):      # an empty variable (compose's ${X:-}) counts as unset
            _drop_copy(environ, name, environ.get(name))
            environ[name] = value
            _APPLIED.add(name)

    mirror(environ)
