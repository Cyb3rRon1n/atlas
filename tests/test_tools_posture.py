from lanxang.alerts import AlertStore
from lanxang.clock import utcnow
from lanxang.config.models import AtlasConfig, UptimeCheck
from lanxang.devices import Sighting
from lanxang.devices.store import InventoryStore
from lanxang.intelligence.tools import _cap, build_tools, execute_tool
from lanxang.monitoring.uptime import UptimeStore
from lanxang.posture.store import PostureStore


NAMES = ("get_posture", "get_devices", "get_alerts", "get_disks", "get_uptime")


def config(**posture):
    settings = AtlasConfig()
    settings.posture.enabled = posture.get("enabled", True)
    settings.posture.internet_view = posture.get("internet_view", False)
    settings.uptime.checks = [UptimeCheck(name="Media", target="192.0.2.5:8096")]
    return settings


def run(settings, name, arguments=None):
    return execute_tool(build_tools(settings), name, arguments or {})


def test_posture_tools_are_registered_and_read_only(isolated_cwd, temp_db):
    tools = build_tools(config())
    assert all(name in tools for name in NAMES)
    assert "get_internet_view" not in tools
    assert "get_internet_view" in build_tools(config(internet_view=True))
    assert not any(word in name for name in tools for word in ("restart", "stop", "delete", "set_"))


def test_cap_reports_the_rest():
    assert _cap(list(range(5)), 2) == {"items": [0, 1], "more": 3}


def test_get_devices_caps_at_40_with_more_count(isolated_cwd, temp_db):
    store = InventoryStore()
    store.record_run("lan", [Sighting("lan", f"aa:{i:03}", ip=f"192.0.2.{i % 250}", mac=f"aa:{i:03}", hostname=f"h{i}")
                             for i in range(300)], now=utcnow())
    store.record_run("lan", [Sighting("lan", "aa:000", ip="192.0.2.0", mac="aa:000", hostname="h0"),
                             Sighting("lan", "bb:new", ip="192.0.2.9", mac="bb:new", hostname="newbie")], now=utcnow())
    result = run(config(), "get_devices")
    assert len(result["items"]) == 40 and result["more"] == 261
    assert len(run(config(), "get_devices", {"limit": 500})["items"]) == 40
    assert len(run(config(), "get_devices", {"limit": 3})["items"]) == 3
    new = run(config(), "get_devices", {"filter": "new"})
    assert new["items"] and all(d["state"] == "new" for d in new["items"])


def test_get_posture_lists_routes_without_sign_in(isolated_cwd, temp_db):
    store = PostureStore()
    store.set_status("tunnel", True, {"connections": 4}, utcnow())
    store.save_routes([
        {"name": "atlas", "hosts": ["atlas.example.test"], "entrypoints": ["tunnel"], "protection": "authelia", "provider": "docker"},
        {"name": "jellyfin", "hosts": ["jf.example.test"], "entrypoints": ["tunnel"], "protection": "", "provider": "docker"},
    ], utcnow())
    result = run(config(), "get_posture")
    assert result["routes"] == 2 and result["unprotected"] == ["jellyfin"]
    assert result["strip"] and "new_destinations" in result


def test_get_alerts_open_and_recent(isolated_cwd, temp_db):
    AlertStore().event("ports", "New open port 22", now=utcnow())
    result = run(config(), "get_alerts")
    assert [a["title"] for a in result["open"]["items"]] == ["New open port 22"]
    assert result["recently_resolved"]["more"] == 0


def test_get_uptime_summary(isolated_cwd, temp_db):
    UptimeStore().save({"Media": (True, 12.0, "ok")}, utcnow())
    result = run(config(), "get_uptime")
    row = result["items"][0]
    assert row["name"] == "Media" and row["up"] is True and row["uptime"]["24 h"] == 100.0


def test_get_disks_from_status(isolated_cwd, temp_db):
    PostureStore().set_status("nas", True, {"name": "nas1", "info": {"disks": [
        {"dev": "sda", "model": "X", "temp": 31, "health": "PASSED", "life": 90}]}}, utcnow())
    item = run(config(), "get_disks")["items"][0]
    assert item["host"] == "nas1" and item["health"] == "PASSED" and item["temp"] == 31


def test_get_internet_view(isolated_cwd, temp_db):
    settings = config(internet_view=True)
    assert run(settings, "get_internet_view")["status"] == "not set up"
    PostureStore().set_status("internet_view", True, {"checked_at": "2026-11-19T10:00", "ip": "192.0.2.10", "ok": True,
                                                     "known": True, "ports": [{"port": 443, "expected": True}],
                                                     "vulns": [], "cpes": [], "error": ""}, utcnow())
    result = run(settings, "get_internet_view")
    assert result["ip"] == "192.0.2.10" and result["ports"][0]["port"] == 443


def test_tools_say_not_set_up(isolated_cwd, temp_db):
    assert run(config(enabled=False), "get_posture")["status"] == "not set up"
    assert run(config(), "get_posture")["status"] == "not set up"
    assert "how" in run(config(), "get_posture")
    assert run(config(), "get_disks")["status"] == "not set up"
    empty = AtlasConfig()
    assert run(empty, "get_uptime")["status"] == "not set up"


def test_tool_limits_tolerate_junk_and_long_details_are_cut(isolated_cwd, temp_db):
    assert run(config(), "get_devices", {"limit": "lots"})["more"] == 0       # junk limit = the default, no error
    AlertStore().event("ports", "New open port 22", detail="x" * 2000, now=utcnow())
    detail = run(config(), "get_alerts")["open"]["items"][0]["detail"]
    assert len(detail) <= 300 and detail.endswith("…")
