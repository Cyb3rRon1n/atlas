from atlas.services import detect_services


def test_detect_services_matches_known_container():

    containers = [
        {"name": "sonarr", "status": "running"},
    ]

    results = detect_services(containers)

    assert len(results) == 1
    assert results[0]["name"] == "sonarr"
    assert results[0]["category"] == "media"
    assert results[0]["container"] == "sonarr"
    assert results[0]["status"] == "running"


def test_detect_services_matches_by_substring():

    containers = [
        {"name": "my-radarr-container", "status": "exited"},
    ]

    results = detect_services(containers)

    assert len(results) == 1
    assert results[0]["name"] == "radarr"


def test_detect_services_ignores_unknown_containers():

    containers = [
        {"name": "some-random-app", "status": "running"},
    ]

    results = detect_services(containers)

    assert results == []
