from pathlib import Path

from lanxang.config import env, local


def test_old_names_fill_new_and_new_wins():
    environ = {"ATLAS_NTFY_TOKEN": "old", "LANXANG_SMTP_PASSWORD": "new", "ATLAS_SMTP_PASSWORD": "stale",
               "ATLAS_EMPTY": "", "LANXANG_EMPTY": "kept"}
    env.mirror(environ)
    assert environ["LANXANG_NTFY_TOKEN"] == "old"          # old-only setting reaches the new name
    assert environ["LANXANG_SMTP_PASSWORD"] == "new"       # both set: the new name keeps its value
    assert environ["ATLAS_EMPTY"] == "kept"                # an empty variable counts as unset
    env.mirror(environ)                                    # idempotent
    assert environ["LANXANG_NTFY_TOKEN"] == "old"


def test_config_file_prefers_lanxang_yaml(isolated_cwd):
    assert local.config_file() == Path("lanxang.yaml")     # neither exists: new installs write the new name
    Path("atlas.yaml").write_text("name: old\n")
    assert local.config_file() == Path("atlas.yaml")       # existing install keeps reading its file
    Path("lanxang.yaml").write_text("name: new\n")
    assert local.config_file() == Path("lanxang.yaml")     # both: the new file wins


def test_atlas_command_still_runs_with_a_notice(monkeypatch, capsys):
    import sys
    from lanxang import cli

    called = []
    monkeypatch.setattr(cli, "app", lambda: called.append(True))
    monkeypatch.setattr(sys, "argv", ["atlas", "status"])
    cli.legacy()
    assert called == [True]
    assert "atlas is now lanxang" in capsys.readouterr().err


def test_config_file_ignores_a_directory_named_lanxang_yaml(isolated_cwd):
    # Docker creates an empty directory when a bind-mount source is missing
    Path("lanxang.yaml").mkdir()
    Path("atlas.yaml").write_text("name: old\n")
    assert local.config_file() == Path("atlas.yaml")
