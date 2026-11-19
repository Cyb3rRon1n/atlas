"""install.sh end to end against fake docker/curl binaries - the real-Docker run is in the PR notes."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from lanxang.config.models import AtlasConfig

REPO = Path(__file__).resolve().parent.parent

FAKE_DOCKER = """#!/bin/sh
echo "docker $*" >> "$FAKE_LOG"
case "$*" in
  *"auth setup-code"*) [ -f "$FAKE_LOG.pw" ] && echo "A password is already set" || echo "c0ffee12" ;;
esac
exit 0
"""


@pytest.fixture
def sandbox(tmp_path):

    if not shutil.which("bash"):
        pytest.skip("needs bash")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER)
    (bin_dir / "curl").write_text("#!/bin/sh\nexit 0\n")
    for tool in ("docker", "curl"):
        (bin_dir / tool).chmod(0o755)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path), "LANXANG_SOURCE": str(REPO),
           "LANXANG_DIR": str(tmp_path / "lanxang"), "FAKE_LOG": str(tmp_path / "docker.log")}

    def run(*args, **extra):
        return subprocess.run([shutil.which("bash"), str(REPO / "install.sh"), *args], env={**env, **extra},
                              capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)

    return tmp_path, run


def test_fresh_install_upgrade_and_uninstall(sandbox):

    home, run = sandbox
    target = home / "lanxang"

    result = run("--yes", LANXANG_BIND="0.0.0.0", LANXANG_AI="ollama", LANXANG_OLLAMA_URL="http://10.1.2.3:11434")
    assert result.returncode == 0, result.stderr
    assert "c0ffee12" in result.stdout

    env = (target / ".env").read_text()
    assert "LANXANG_BIND=0.0.0.0" in env and "LANXANG_PORT=8420" in env
    assert "LANXANG_CONFIG" not in env
    assert "LANXANG_TAG=latest" in env
    assert oct((target / ".env").stat().st_mode & 0o777) == "0o600"
    config = AtlasConfig(**yaml.safe_load((target / "lanxang.yaml").read_text()))
    assert config.intelligence.provider == "ollama" and config.intelligence.ollama_host == "http://10.1.2.3:11434"
    assert config.web.auth == "builtin"
    assert oct((target / "lanxang.yaml").stat().st_mode & 0o777) == "0o644"   # read by the container user
    assert (target / "docker-compose.yml").read_text() == (REPO / "docker-compose.yml").read_text()
    assert "compose up -d" in (home / "docker.log").read_text()

    (target / "lanxang.yaml").write_text("name: mine\n")
    (home / "docker.log.pw").touch()
    result = run("--yes", LANXANG_REF="v9.9.9")
    assert result.returncode == 0, result.stderr
    assert "Upgrade" in result.stdout and "setup code" not in result.stdout
    assert (target / "lanxang.yaml").read_text() == "name: mine\n"
    assert "LANXANG_TAG=9.9.9" in (target / ".env").read_text() and "LANXANG_BIND=0.0.0.0" in (target / ".env").read_text()

    result = run("--uninstall", "--yes")
    assert result.returncode == 0 and target.exists()
    assert "compose down" in (home / "docker.log").read_text() and "down -v" not in (home / "docker.log").read_text()


def test_refuses_without_docker(sandbox):

    home, run = sandbox
    os.remove(home / "bin" / "docker")

    result = run("--yes", PATH=f"{home / 'bin'}:/nonexistent")

    assert result.returncode != 0 and "Docker is not installed" in result.stderr


def test_piped_install_survives_docker_reading_stdin(sandbox):
    # `curl ... | bash`: bash reads the script from stdin, and docker commands inherit that stdin. A real
    # `docker compose` read the rest of the script, so the installer stopped silently after "Started".
    home, run = sandbox
    (home / "bin" / "docker").write_text(FAKE_DOCKER.replace('echo "docker $*"', 'cat >/dev/null; echo "docker $*"'))
    env = {"PATH": f"{home / 'bin'}:/usr/bin:/bin", "HOME": str(home), "LANXANG_SOURCE": str(REPO),
           "LANXANG_DIR": str(home / "lanxang"), "FAKE_LOG": str(home / "docker.log"), "LANXANG_BIND": "0.0.0.0"}
    result = subprocess.run([shutil.which("bash")], input=(REPO / "install.sh").read_text(), env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "Lanxang is running" in result.stdout and "c0ffee12" in result.stdout


def test_no_ai_choice_leaves_the_ai_section_to_the_setup_page(sandbox):
    home, run = sandbox
    assert run("--yes").returncode == 0
    written = yaml.safe_load((home / "lanxang" / "lanxang.yaml").read_text())
    assert "intelligence" not in written and written["web"]["auth"] == "builtin"


def test_upgrade_keeps_the_new_name_when_both_are_set_and_clears_a_docker_folder(sandbox):
    home, run = sandbox
    old = home / "atlas"
    old.mkdir()
    (old / "docker-compose.yml").write_text("services: {}\n")
    (old / ".env").write_text("ATLAS_PORT=8420\nLANXANG_PORT=9000\nATLAS_BIND=0.0.0.0\nLANXANG_CONFIG=atlas.yaml\n")
    (old / "atlas.yaml").write_text("name: mine\n")
    (old / "lanxang.yaml").mkdir()                       # what docker leaves when the mounted file is missing
    result = run("--yes", LANXANG_DIR="", HOME=str(home))
    assert result.returncode == 0, result.stderr
    assert (old / "lanxang.yaml").read_text() == "name: mine\n"
    env = (old / ".env").read_text().splitlines()
    assert [line for line in env if "PORT" in line] == ["LANXANG_PORT=9000"]
    assert "LANXANG_BIND=0.0.0.0" in env and not any("CONFIG" in line or "ATLAS_" in line for line in env)


def test_old_atlas_install_is_upgraded_in_place_and_keeps_its_config(sandbox):
    home, run = sandbox
    old = home / "atlas"
    old.mkdir()
    (old / "docker-compose.yml").write_text("services: {}\n")
    (old / ".env").write_text("ATLAS_PORT=8420\nATLAS_TAG=0.12.1\n")
    (old / "atlas.yaml").write_text("name: mine\njellyfin:\n  api_key: ${ATLAS_JELLYFIN_KEY}\n")
    # no LANXANG_DIR: the installer must find ~/atlas by itself
    result = run("--yes", LANXANG_DIR="", HOME=str(home))
    assert result.returncode == 0, result.stderr
    assert not (home / "lanxang").exists() and not (old / "atlas.yaml").exists()
    assert (old / "lanxang.yaml").read_text() == "name: mine\njellyfin:\n  api_key: ${LANXANG_JELLYFIN_KEY}\n"
    assert "${ATLAS_JELLYFIN_KEY}" in (old / "lanxang.yaml.before-1.3").read_text()
    env = (old / ".env").read_text()
    assert "LANXANG_PORT=8420" in env and "ATLAS_" not in env and "LANXANG_CONFIG" not in env
    assert (old / ".env.before-1.3").read_text() == "ATLAS_PORT=8420\nATLAS_TAG=0.12.1\n"
    assert (old / "docker-compose.yml").read_text() == (REPO / "docker-compose.yml").read_text()
