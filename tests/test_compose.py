from atlas.compose import parse_compose_file


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
