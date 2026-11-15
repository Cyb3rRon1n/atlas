from datetime import datetime

from atlas.config.models import AtlasConfig, HealthConfig
from atlas.health.alerts import alerts, assess, container_problem, container_state, run
from atlas.posture.store import PostureStore
from atlas.web.home_page import build_hosts


NOW = datetime(2026, 11, 15, 12, 0)


def c(name, status="running", health="", exit_code=0, on_demand=False):
    return {"name": name, "status": status, "health": health, "exit_code": exit_code, "on_demand": on_demand}


def health(**over):
    base = {"max_temperature_c_by_sensor": {"coretemp": 60.0}, "temperature_high_c_by_sensor": {"coretemp": 88.0},
            "memory_percent": 40.0, "disks": {"root disk": 30.0}, "status_feeds": {}}
    return {**base, **over}


def kinds(issues):
    return sorted((i["kind"], i["subject"]) for i in issues)


def test_clean_exit_and_on_demand_are_asleep_crashes_are_problems():
    assert container_state(c("game-room", "exited", exit_code=0)) == "asleep"
    assert container_state(c("helper", "exited", exit_code=137, on_demand=True)) == "asleep"
    assert container_state(c("never-started", "created", exit_code=None)) == "asleep"
    assert container_state(c("web")) == "ok"
    assert container_problem(c("app", "exited", exit_code=1)) == "app stopped (exit code 1)"
    assert container_problem(c("app", "restarting")) == "app keeps restarting"
    assert container_problem(c("db", health="unhealthy")) == "db unhealthy"
    assert container_problem(c("game-room", "exited")) is None


def test_quiet_host_has_no_issues():
    issues, state = assess(health(), [c("web"), c("game-room", "exited")], HealthConfig(), {})
    assert issues == [] and state == {"hot": {}}


def test_temperature_needs_two_samples_near_the_sensor_limit():
    hot = health(max_temperature_c_by_sensor={"coretemp": 84.0, "nvme": 90.0})   # nvme has no limit: skipped
    issues, state = assess(hot, [], HealthConfig(), {})
    assert issues == [] and state["hot"] == {"coretemp": 1}
    issues, state = assess(hot, [], HealthConfig(), state)
    assert kinds(issues) == [("temperature", "coretemp")] and "limit is 88°C" in issues[0]["detail"]
    assert assess(health(), [], HealthConfig(), state)[1]["hot"] == {}         # cooled down: counter resets


def test_memory_disks_containers_and_feeds():
    issues, _ = assess(health(memory_percent=95.0, disks={"root disk": 50.0, "media array": 93.0},
                              status_feeds={"raid card": {"state": "warn", "temp": 86},
                                            "offline feed": {"error": "timed out"}}),
                       [c("app", "exited", exit_code=2), c("game-room", "exited")], HealthConfig(), {})
    assert kinds(issues) == [("container", "app"), ("disk", "media array"), ("feed", "raid card"),
                             ("memory", "memory")]
    assert "86°C" in next(i["detail"] for i in issues if i["kind"] == "feed")


def test_alerts_once_and_on_recovery(temp_db):
    store, sent, settings = PostureStore(temp_db), [], AtlasConfig()
    run(settings, store, health(memory_percent=95.0), [], NOW, send=sent.append)
    run(settings, store, health(memory_percent=96.0), [], NOW, send=sent.append)
    assert len(sent) == 1 and "Memory almost full" in sent[0]
    run(settings, store, health(), [], NOW, send=sent.append)
    assert "Resolved" in sent[-1] and len(sent) == 2
    assert alerts([], []) == []


def test_alerts_can_be_turned_off(temp_db):
    sent, settings = [], AtlasConfig(health={"alerts": False})
    issues = run(settings, PostureStore(temp_db), health(memory_percent=99.0), [], NOW, send=sent.append)
    assert sent == [] and issues                      # still recorded for the home page


def test_home_card_lists_asleep_rooms_apart_and_stays_green():
    topology = {"docker": {"networks": {"net": [c("web"), c("game-room", "exited"), c("solo", "exited")]}}}
    hosts = build_hosts(topology, {"load_average": [1.0], "cpu_count": 8}, None)
    row = hosts["rows"][0]
    assert row["problems"] == [] and row["asleep"] == ["game-room", "solo"] and hosts["state"] == "ok"
    hot = [{"kind": "temperature", "detail": "coretemp at 86°C"}, {"kind": "container", "detail": "dup"}]
    row = build_hosts(topology, {"load_average": [1.0], "cpu_count": 8}, None, hot)["rows"][0]
    assert row["problems"] == ["coretemp at 86°C"]
