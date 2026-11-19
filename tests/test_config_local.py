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
    for key in [k for k in environ if k.startswith(("ATLAS_", "LANXANG_", "ANTHROPIC_"))]:
        environ.pop(key)
    monkeypatch.setattr(os, "environ", environ)
    monkeypatch.setattr(local, "_APPLIED", set())
    return environ


def test_web_settings_fill_in_what_atlas_yaml_leaves_out(env, isolated_cwd):
    (isolated_cwd / "lanxang.yaml").write_text("name: mine\nnotify:\n  ntfy:\n    topic: from-yaml\n")
    local.save_settings({"notify": {"ntfy": {"url": "https://ntfy.example.org", "topic": "from-web"}},
                         "proxmox": {"enabled": True, "host": "192.0.2.5"}})

    config = load_config()
    assert config.name == "mine"
    assert config.notify.ntfy.topic == "from-yaml"                     # lanxang.yaml wins
    assert config.notify.ntfy.url == "https://ntfy.example.org"        # the web fills the gap
    assert config.proxmox.enabled is True and config.proxmox.host == "192.0.2.5"
    assert local.locked(("notify", "ntfy", "topic")) and not local.locked(("notify", "ntfy", "url"))


def test_saving_merges_and_none_removes(env):
    local.save_settings({"proxmox": {"host": "192.0.2.5", "user": "atlas@pve"}})
    local.save_settings({"proxmox": {"user": None, "enabled": True}})
    assert local.read_settings() == {"proxmox": {"host": "192.0.2.5", "enabled": True}}


def test_secrets_are_private_never_listed_and_env_wins(env, isolated_cwd):
    local.save_secrets({"LANXANG_UNIFI_PASS": "s3cret", "LANXANG_NTFY_TOKEN": "tk"})
    path = isolated_cwd / "inventory" / "secrets.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert local.secret_names() == {"LANXANG_UNIFI_PASS", "LANXANG_NTFY_TOKEN"}

    env["LANXANG_NTFY_TOKEN"] = "from-dotenv"
    load_config()
    assert env["LANXANG_UNIFI_PASS"] == "s3cret" and env["LANXANG_NTFY_TOKEN"] == "from-dotenv"


def test_changed_and_removed_secrets_take_effect_without_restart(env):
    local.save_secrets({"LANXANG_UNIFI_PASS": "old"})
    load_config()
    local.save_secrets({"LANXANG_UNIFI_PASS": "new"})
    load_config()
    assert env["LANXANG_UNIFI_PASS"] == "new"
    local.save_secrets({"LANXANG_UNIFI_PASS": None})
    load_config()
    assert "LANXANG_UNIFI_PASS" not in env and local.secret_names() == set()


def test_settings_reference_stored_secrets(env):
    local.save_settings({"proxmox": {"token_value": "${LANXANG_PROXMOX_TOKEN}"}})
    local.save_secrets({"LANXANG_PROXMOX_TOKEN": "abc-123"})
    assert load_config().proxmox.token_value == "abc-123"


def test_broken_files_never_stop_atlas(env, isolated_cwd):
    (isolated_cwd / "inventory").mkdir()
    (isolated_cwd / "inventory" / "settings.yaml").write_text(": not [yaml")
    (isolated_cwd / "inventory" / "secrets.json").write_text("{nope")
    assert load_config().name == "atlas-node"


def test_secret_values_never_reach_the_settings_file(env, isolated_cwd):
    with pytest.raises(ValueError):
        local.save_secrets({"not-an-env-name": "x"})
    local.save_secrets({"LANXANG_SMTP_PASSWORD": "pw"})
    assert "pw" not in json.dumps(local.read_settings())


def test_apply_secrets_follows_changes(env):
    local.save_secrets({"LANXANG_UNIFI_PASS": "old"})
    local.apply_secrets()
    assert env["LANXANG_UNIFI_PASS"] == "old"
    local.save_secrets({"LANXANG_UNIFI_PASS": "new"})
    local.apply_secrets()
    assert env["LANXANG_UNIFI_PASS"] == "new"
    local.save_secrets({"LANXANG_UNIFI_PASS": None})
    local.apply_secrets()
    assert "LANXANG_UNIFI_PASS" not in env                                  # nothing resurrects it


def test_apply_secrets_never_touches_a_real_variable(env):
    env["LANXANG_NTFY_TOKEN"] = "real"
    local.save_secrets({"LANXANG_NTFY_TOKEN": "saved", "LANXANG_UNIFI_PASS": "x"})
    local.apply_secrets()
    assert env["LANXANG_NTFY_TOKEN"] == "real"
    local.save_secrets({"LANXANG_NTFY_TOKEN": None, "LANXANG_UNIFI_PASS": None})
    local.apply_secrets()
    assert env["LANXANG_NTFY_TOKEN"] == "real"


def test_an_old_atlas_keyed_secrets_file_can_be_replaced_and_cleared(env, isolated_cwd):
    path = isolated_cwd / "inventory" / "secrets.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"ATLAS_UNIFI_PASS": "old"}))
    load_config()
    assert env["LANXANG_UNIFI_PASS"] == "old" and local.secret_names() == {"LANXANG_UNIFI_PASS"}
    local.save_secrets({"LANXANG_UNIFI_PASS": "new"})
    assert json.loads(path.read_text()) == {"LANXANG_UNIFI_PASS": "new"}
    load_config()
    assert env["LANXANG_UNIFI_PASS"] == "new"
    local.save_secrets({"LANXANG_UNIFI_PASS": None})
    load_config()
    assert json.loads(path.read_text()) == {} and "LANXANG_UNIFI_PASS" not in env

