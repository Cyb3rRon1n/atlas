from lanxang.compose import parse_compose_file


COMPOSE_YAML = """
services:
  plex:
    image: plexinc/pms-docker
    ports:
      - "32400:32400"
    volumes:
      - /data/media:/data
  sonarr:
    image: linuxserver/sonarr
"""


def test_parse_compose_file_returns_none_when_missing(tmp_path):

    result = parse_compose_file(
        tmp_path / "does-not-exist.yml"
    )

    assert result is None


def test_parse_compose_file_parses_services(tmp_path):

    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(COMPOSE_YAML)

    project = parse_compose_file(compose_file)

    assert project.name == tmp_path.name
    assert len(project.services) == 2

    plex = next(
        s for s in project.services if s.name == "plex"
    )

    assert plex.image == "plexinc/pms-docker"
    assert plex.ports == ["32400:32400"]
    assert plex.volumes == ["/data/media:/data"]

    sonarr = next(
        s for s in project.services if s.name == "sonarr"
    )

    assert sonarr.image == "linuxserver/sonarr"
    assert sonarr.ports == []


def test_atlas_scan_runs_posture_watch_with_net_admin():
    import yaml
    data = yaml.safe_load(open("docker-compose.yml"))
    scan = data["services"]["atlas-scan"]
    assert "NET_ADMIN" in scan["cap_add"]
    assert "while :; do lanxang posture watch; sleep 30; done &" in "\n".join(scan["command"])   # restarts if it dies
    assert "lanxang uptime check" in "\n".join(scan["command"]) and "lanxang ups check" in "\n".join(scan["command"])


def test_docker_proxy_allows_what_the_container_list_reads():
    import yaml
    env = yaml.safe_load(open("docker-compose.yml"))["services"]["docker-proxy"]["environment"]
    # collect_containers() reads container.image.tags -> GET /images/<id>/json
    assert env["CONTAINERS"] == 1 and env["IMAGES"] == 1
    assert env["POST"] == "${LANXANG_DOCKER_WRITE:-0}"   # writes stay off by default


def test_service_names_and_old_env_names_survive_the_rename():
    import yaml
    data = yaml.safe_load(open("docker-compose.yml"))
    assert {"atlas", "atlas-scan"} <= set(data["services"])   # existing overrides name these
    web = data["services"]["atlas"]
    assert web["image"] == "ghcr.io/cyb3rron1n/lanxang:${LANXANG_TAG:-latest}"
    assert "${LANXANG_PORT:-8420}" in web["ports"][0]


def _mount_sources(tmp_path, env_text):
    import json
    import shutil
    import subprocess
    import pytest
    if not shutil.which("docker"):
        pytest.skip("needs docker")
    shutil.copy("docker-compose.yml", tmp_path / "docker-compose.yml")
    (tmp_path / ".env").write_text(env_text)
    out = subprocess.run(["docker", "compose", "config", "--format", "json"], cwd=tmp_path, capture_output=True,
                         text=True, check=True).stdout
    return {v["source"].rsplit("/", 1)[1] for v in json.loads(out)["services"]["atlas"]["volumes"]
            if v.get("type") == "bind"}


def test_compose_mounts_lanxang_yaml(tmp_path):
    (tmp_path / "lanxang.yaml").write_text("name: mine\n")
    assert "lanxang.yaml" in _mount_sources(tmp_path, "LANXANG_CONFIG=atlas.yaml\n")   # a stale variable is ignored


def test_an_atlas_scan_minutes_override_is_not_shadowed():
    import yaml
    scan = yaml.safe_load(open("docker-compose.yml"))["services"]["atlas-scan"]
    assert not any("SCAN_MINUTES" in k for k in scan["environment"])
    assert "$${LANXANG_SCAN_MINUTES:-15}" in "\n".join(scan["command"])
