from atlas.intelligence.context import AtlasEnvironmentContext
from atlas.knowledge.store import KnowledgeStore
from atlas.reporting.trends import build_trends_payload


def test_build_trends_payload_empty_when_nothing_stored(temp_db):

    assert build_trends_payload() == {"host": {}, "containers": {}, "guests": {}}


def test_build_trends_payload_reports_host_and_container_summaries(temp_db):

    store = KnowledgeStore()

    for cpu_value in (10.0, 20.0, 30.0):

        environment = AtlasEnvironmentContext()

        environment.update("monitoring", {
            "metrics": {"cpu_percent": cpu_value, "memory_percent": None},
            "containers": {"plex": {"cpu_percent": cpu_value / 2}}
        })

        store.save_environment(environment)

    payload = build_trends_payload()

    assert payload["host"]["cpu_percent"] == {
        "latest": 30.0, "min": 10.0, "max": 30.0, "avg": 20.0, "samples": 3
    }
    assert "memory_percent" not in payload["host"]
    assert payload["containers"]["plex"]["cpu_percent"] == {
        "latest": 15.0, "min": 5.0, "max": 15.0, "avg": 10.0, "samples": 3
    }


def test_build_trends_payload_reports_guest_summaries(temp_db):

    store = KnowledgeStore()

    for cpu_value in (0.10, 0.20, 0.30):

        environment = AtlasEnvironmentContext()

        environment.update("virtualization", {
            "nodes": [],
            "guests": [
                {
                    "vmid": 100, "name": "plex", "cpu": cpu_value,
                    "maxcpu": 4, "mem": 1_000_000, "maxmem": 4_000_000
                }
            ]
        })

        store.save_environment(environment)

    payload = build_trends_payload()

    assert payload["guests"]["100"]["name"] == "plex"
    assert payload["guests"]["100"]["cpu_percent"] == {
        "latest": 30.0, "min": 10.0, "max": 30.0, "avg": 20.0, "samples": 3
    }


def test_build_trends_payload_respects_limit(temp_db):

    store = KnowledgeStore()

    for cpu_value in (10.0, 20.0, 30.0, 40.0):

        environment = AtlasEnvironmentContext()
        environment.update("monitoring", {"metrics": {"cpu_percent": cpu_value}, "containers": {}})
        store.save_environment(environment)

    payload = build_trends_payload(limit=2)

    # Only the two most recent rows (30.0, 40.0) are in scope.
    assert payload["host"]["cpu_percent"]["min"] == 30.0
    assert payload["host"]["cpu_percent"]["max"] == 40.0
    assert payload["host"]["cpu_percent"]["samples"] == 2
