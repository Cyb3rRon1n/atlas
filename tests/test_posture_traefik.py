from atlas.posture.collectors.traefik import collect_routes, routes_from_files, routes_from_labels


CONTAINERS = [
    {"name": "atlas", "labels": {
        "traefik.enable": "true",
        "traefik.http.routers.atlas.rule": "Host(`atlas.example.test`)",
        "traefik.http.routers.atlas.entrypoints": "websecure,tunnel",
        "traefik.http.routers.atlas.middlewares": "authelia@docker"}},
    {"name": "jellyfin", "labels": {
        "traefik.enable": "true",
        "traefik.http.routers.jellyfin.rule": "Host(`jellyfin.example.test`) || Host(`jf.example.test`)",
        "traefik.http.routers.jellyfin.entrypoints": "websecure"}},
    {"name": "hidden", "labels": {"traefik.http.routers.x.rule": "Host(`x.example.test`)"}},
    {"name": "plain", "labels": {}},
]


def test_routes_from_labels_reads_rule_entrypoints_and_protection():
    routes = routes_from_labels(CONTAINERS, "authelia")
    assert routes == [
        {"name": "atlas", "hosts": ["atlas.example.test"], "entrypoints": ["websecure", "tunnel"],
         "protection": "authelia", "provider": "docker"},
        {"name": "jellyfin", "hosts": ["jellyfin.example.test", "jf.example.test"], "entrypoints": ["websecure"],
         "protection": "public", "provider": "docker"},
    ]


def test_routes_from_files_reads_dynamic_yaml_and_skips_backups(tmp_path):
    (tmp_path / "immich.yml").write_text(
        "http:\n  routers:\n    immich:\n      rule: Host(`immich.example.test`)\n"
        "      entryPoints: [websecure, tunnel]\n      middlewares: [crowdsec@docker]\n"
        "    api:\n      rule: Host(`traefik.example.test`)\n      service: api@internal\n"
        "      middlewares: [authelia@docker]\n")
    (tmp_path / "immich.yml.bak-1").write_text("http: {routers: {old: {rule: 'Host(`old.example.test`)'}}}")
    (tmp_path / "tls.yml").write_text("tls:\n  options: {}\n")
    (tmp_path / "broken.yml").write_text(":\n  - [")
    routes = routes_from_files(tmp_path, "authelia")
    assert [r["name"] for r in routes] == ["api", "immich"]
    assert routes[1] == {"name": "immich", "hosts": ["immich.example.test"], "entrypoints": ["websecure", "tunnel"],
                         "protection": "public", "provider": "file"}
    assert routes[0]["protection"] == "authelia"


def test_routes_from_files_with_no_directory_is_empty():
    assert routes_from_files("", "authelia") == []


def test_collect_routes_merges_docker_and_files(tmp_path):
    (tmp_path / "a.yml").write_text("http:\n  routers:\n    a:\n      rule: Host(`a.example.test`)\n")

    class C:
        def __init__(self, name, labels):
            self.name, self.labels = name, labels

    class Client:
        class containers:
            @staticmethod
            def list():
                return [C(c["name"], c["labels"]) for c in CONTAINERS]

    names = [r["name"] for r in collect_routes(Client, str(tmp_path), "authelia")]
    assert names == ["a", "atlas", "jellyfin"]


def test_auth_middleware_must_match_exactly():
    containers = [{"name": n, "labels": {"traefik.enable": "true",
                                         f"traefik.http.routers.{n}.rule": f"Host(`{n}.example.test`)",
                                         f"traefik.http.routers.{n}.middlewares": mw}}
                  for n, mw in (("a", "authelia-headers@docker"), ("b", "authelia"), ("c", "crowdsec,authelia@file"))]
    assert {r["name"]: r["protection"] for r in routes_from_labels(containers, "authelia")} == {
        "a": "public", "b": "authelia", "c": "authelia"}
