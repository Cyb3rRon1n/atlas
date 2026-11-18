import json
import os
import stat

import pytest

from lanxang.config import local
from lanxang.config.loader import load_config


@pytest.fixture
def env(isolated_cwd, monkeypatch):
    """A private copy of the environment, so stored secrets applied by load_config never leak between tests."""

    environ = dict(os.environ)
    for key in [k for k in environ if k.startswith(("ATLAS_", "ANTHROPIC_"))]:
        environ.pop(key)
    monkeypatch.setattr(os, "environ", environ)
    monkeypatch.setattr(local, "_APPLIED", set())
    return environ


def test_web_settings_fill_in_what_atlas_yaml_leaves_out(env, isolated_cwd):
    (isolated_cwd / "atlas.yaml").write_text("name: mine\nnotify:\n  ntfy:\n    topic: from-yaml\n")
    local.save_settings({"notify": {"ntfy": {"url": "https://ntfy.example.org", "topic": "from-web"}},
                         "proxmox": {"enabled": True, "host": "192.0.2.5"}})

    config = load_config()
    assert config.name == "mine"
    assert config.notify.ntfy.topic == "from-yaml"                     # atlas.yaml wins
    assert config.notify.ntfy.url == "https://ntfy.example.org"        # the web fills the gap
    assert config.proxmox.enabled is True and config.proxmox.host == "192.0.2.5"
    assert local.locked(("notify", "ntfy", "topic")) and not local.locked(("notify", "ntfy", "url"))


def test_saving_merges_and_none_removes(env):
    local.save_settings({"proxmox": {"host": "192.0.2.5", "user": "atlas@pve"}})
    local.save_settings({"proxmox": {"user": None, "enabled": True}})
    assert local.read_settings() == {"proxmox": {"host": "192.0.2.5", "enabled": True}}


def test_secrets_are_private_never_listed_and_env_wins(env, isolated_cwd):
    local.save_secrets({"ATLAS_UNIFI_PASS": "s3cret", "ATLAS_NTFY_TOKEN": "tk"})
    path = isolated_cwd / "inventory" / "secrets.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert local.secret_names() == {"ATLAS_UNIFI_PASS", "ATLAS_NTFY_TOKEN"}

    env["ATLAS_NTFY_TOKEN"] = "from-dotenv"
    load_config()
    assert env["ATLAS_UNIFI_PASS"] == "s3cret" and env["ATLAS_NTFY_TOKEN"] == "from-dotenv"


def test_changed_and_removed_secrets_take_effect_without_restart(env):
    local.save_secrets({"ATLAS_UNIFI_PASS": "old"})
    load_config()
    local.save_secrets({"ATLAS_UNIFI_PASS": "new"})
    load_config()
    assert env["ATLAS_UNIFI_PASS"] == "new"
    local.save_secrets({"ATLAS_UNIFI_PASS": None})
    load_config()
    assert "ATLAS_UNIFI_PASS" not in env and local.secret_names() == set()


def test_settings_reference_stored_secrets(env):
    local.save_settings({"proxmox": {"token_value": "${ATLAS_PROXMOX_TOKEN}"}})
    local.save_secrets({"ATLAS_PROXMOX_TOKEN": "abc-123"})
    assert load_config().proxmox.token_value == "abc-123"


def test_broken_files_never_stop_atlas(env, isolated_cwd):
    (isolated_cwd / "inventory").mkdir()
    (isolated_cwd / "inventory" / "settings.yaml").write_text(": not [yaml")
    (isolated_cwd / "inventory" / "secrets.json").write_text("{nope")
    assert load_config().name == "atlas-node"


def test_secret_values_never_reach_the_settings_file(env, isolated_cwd):
    with pytest.raises(ValueError):
        local.save_secrets({"not-an-env-name": "x"})
    local.save_secrets({"ATLAS_SMTP_PASSWORD": "pw"})
    assert "pw" not in json.dumps(local.read_settings())
