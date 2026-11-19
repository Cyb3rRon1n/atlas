"""Since 1.3 only the Lanxang names are read; what an older install still has is named in a warning."""

import json
import logging
import os
from pathlib import Path

from lanxang.config import local
from lanxang.config.loader import load_config


def test_only_lanxang_yaml_is_read(isolated_cwd):
    Path("atlas.yaml").write_text("name: old\n")
    assert local.config_file() == Path("lanxang.yaml")
    assert load_config().name != "old"


def test_old_names_are_listed(isolated_cwd):
    assert local.old_names({"ATLAS_EMPTY": "", "LANXANG_PORT": "1"}) == []
    Path("atlas.yaml").write_text("name: old\n")
    assert local.old_names({"ATLAS_PORT": "8420"}) == ["atlas.yaml", "ATLAS_PORT"]
    Path("lanxang.yaml").write_text("jellyfin:\n  api_key: ${ATLAS_JELLYFIN_KEY}\n")
    assert local.old_names({}) == ["${ATLAS_...} in lanxang.yaml"]


def test_load_config_warns_once_about_old_names(isolated_cwd, monkeypatch, caplog):
    monkeypatch.setenv("ATLAS_UNIFI_PASS", "pw")
    monkeypatch.setattr(load_config, "_noticed", False, raising=False)
    with caplog.at_level(logging.WARNING, logger="lanxang"):
        load_config()
        load_config()
    warnings = [r.getMessage() for r in caplog.records if "No longer read" in r.getMessage()]
    assert len(warnings) == 1 and "ATLAS_UNIFI_PASS" in warnings[0]


def test_atlas_env_names_are_not_read(isolated_cwd, monkeypatch):
    monkeypatch.setenv("ATLAS_NTFY_TOKEN", "old")
    monkeypatch.setenv("LANXANG_NTFY_TOKEN", "")
    load_config()
    assert not os.environ.get("LANXANG_NTFY_TOKEN")


def test_secrets_saved_under_old_names_still_load(isolated_cwd):
    path = Path("inventory/secrets.json")
    path.parent.mkdir()
    path.write_text(json.dumps({"ATLAS_UNIFI_PASS": "old", "ATLAS_NTFY_TOKEN": "stale", "LANXANG_NTFY_TOKEN": "new"}))
    assert local.secret_names() == {"LANXANG_UNIFI_PASS", "LANXANG_NTFY_TOKEN"}
    assert local._read_secrets()["LANXANG_NTFY_TOKEN"] == "new"               # the new name wins
    local.save_secrets({"LANXANG_SMTP_PASSWORD": "pw"})
    assert json.loads(path.read_text()) == {"LANXANG_UNIFI_PASS": "old", "LANXANG_NTFY_TOKEN": "new",
                                            "LANXANG_SMTP_PASSWORD": "pw"}  # rewritten under the new names


def test_old_references_in_saved_settings_still_resolve(isolated_cwd):
    Path("inventory").mkdir()
    Path("inventory/settings.yaml").write_text("notify:\n  ntfy:\n    token: ${ATLAS_NTFY_TOKEN}\n")
    assert local.read_settings()["notify"]["ntfy"]["token"] == "${LANXANG_NTFY_TOKEN}"


def test_no_atlas_command():
    import tomllib
    scripts = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts == {"lanxang": "lanxang.cli:app"}


def test_a_docker_made_folder_is_named(isolated_cwd):
    Path("lanxang.yaml").mkdir()
    Path("atlas.yaml").write_text("name: old\n")
    assert local.old_names({}) == ["lanxang.yaml is a folder, not your config file"]
