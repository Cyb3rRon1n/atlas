from datetime import datetime, timedelta

from atlas.config.models import MapHost
from atlas.devices import Sighting
from atlas.devices.store import InventoryStore


T0 = datetime(2026, 9, 29, 12, 0)


def at(minutes):

    return T0 + timedelta(minutes=minutes)


def by_name(store):

    return {device["name"]: device for device in store.devices(now=at(999))}


def test_manual_hosts_import_once_as_known(temp_db):

    store = InventoryStore(temp_db)
    hosts = [MapHost(name="mediabox", address="192.168.10.57", role="LXC")]

    assert store.import_manual_hosts(hosts, now=T0) == 1
    assert store.import_manual_hosts(hosts, now=T0) == 0

    device = by_name(store)["mediabox"]
    assert device["state"] == "known"
    assert device["status"] == "invisible"
    assert device["notes"] == "LXC"


def test_lan_sighting_joins_configured_host_and_proxmox_name_is_suggested(temp_db):

    store = InventoryStore(temp_db)
    store.import_manual_hosts([MapHost(name="mediabox", address="192.168.10.57")], now=T0)

    store.record_run("lan", [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57")], now=at(0))
    result = store.record_run("proxmox", [Sighting("proxmox", "pve:200", hostname="mediabox",
                                                   detail={"type": "lxc"})], now=at(0))

    devices = store.devices(now=at(0))
    mediabox = [d for d in devices if d["state"] == "known"][0]
    guest = [d for d in devices if d["state"] == "new"][0]

    assert {s["source"] for s in mediabox["sightings"]} == {"manual", "lan"}
    assert mediabox["status"] == "seen"
    assert guest["suggested_merge_id"] == mediabox["id"]
    assert guest["kind"] == "lxc"
    assert result["suggested"] == 1


def test_first_run_is_baseline_without_alerts_then_new_devices_alert(temp_db):

    store = InventoryStore(temp_db)

    first = store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01", hostname="router.lan")], now=at(0))
    assert first["baseline"] is True
    assert store.due_notifications(now=at(0)) == {}

    second = store.record_run("lan", [Sighting("lan", "aa:02", ip="192.168.10.2", mac="aa:02")], now=at(15))
    assert second["new"] == ["192.168.10.2"]
    assert [item["device"] for item in store.due_notifications(now=at(15))["new"]] == ["192.168.10.2"]
    assert by_name(store)["router"]["name"] == "router"


def test_empty_first_run_does_not_consume_baseline(temp_db):

    store = InventoryStore(temp_db)

    empty = store.record_run("lan", [], now=at(0))
    assert empty["baseline"] is True

    first_real = store.record_run(
        "lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(15))

    assert first_real["baseline"] is True
    assert store.due_notifications(now=at(15)) == {}


def test_resighting_updates_not_duplicates(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.9", mac="aa:01")], now=at(15))

    devices = store.devices(now=at(15))
    assert len(devices) == 1
    assert devices[0]["ip"] == "192.168.10.9"
    assert len(devices[0]["sightings"]) == 1


def test_failed_run_does_not_make_devices_quiet(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.record_run("lan", [], ok=False, error="boom", now=at(15))
    store.record_run("lan", [], ok=False, error="boom", now=at(30))

    assert store.devices(now=at(30))[0]["status"] == "seen"
    assert store.source_runs()[0]["error"] == "boom"


def test_record_run_prunes_old_runs_keeping_newest_50(temp_db):

    store = InventoryStore(temp_db)

    for minute in range(60):
        store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(minute))

    runs = store.source_runs(limit=1000)
    assert len(runs) == 50
    assert runs[0]["started_at"] == at(59).isoformat()

    # status/coverage still work off the surviving rows
    assert store.devices(now=at(59))[0]["status"] == "seen"
    coverage = store.coverage()
    assert coverage["sources"][0]["last_ok"] == at(59).isoformat()


def test_new_alert_suppressed_for_ignored_device(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.record_run("lan", [Sighting("lan", "aa:02", ip="192.168.10.2", mac="aa:02")], now=at(15))

    device = [d for d in store.devices(now=at(15)) if d["ip"] == "192.168.10.2"][0]
    store.set_fields(device["id"], {"state": "ignored"}, now=at(15))

    assert store.due_notifications(now=at(15)) == {}


def test_new_alert_suppressed_once_device_marked_known(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.record_run("lan", [Sighting("lan", "aa:02", ip="192.168.10.2", mac="aa:02")], now=at(15))

    device = [d for d in store.devices(now=at(15)) if d["ip"] == "192.168.10.2"][0]
    store.set_fields(device["id"], {"state": "known"}, now=at(15))

    assert store.due_notifications(now=at(15)) == {}


def test_offline_alert_suppressed_once_device_seen_again(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.set_fields(store.devices()[0]["id"], {"important": True})

    store.record_run("lan", [], now=at(15))
    store.record_run("lan", [], now=at(30))
    store.queue_offline(now=at(30))

    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(45))

    assert store.due_notifications(now=at(45)) == {}


def test_suppressed_notification_is_not_resurrected_later(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.record_run("lan", [Sighting("lan", "aa:02", ip="192.168.10.2", mac="aa:02")], now=at(15))

    device = [d for d in store.devices(now=at(15)) if d["ip"] == "192.168.10.2"][0]
    store.set_fields(device["id"], {"state": "ignored"}, now=at(15))
    assert store.due_notifications(now=at(15)) == {}

    # Flipping back to "new" doesn't resurrect the already-suppressed note.
    store.set_fields(device["id"], {"state": "new"}, now=at(16))
    assert store.due_notifications(now=at(16)) == {}


def test_important_device_offline_queues_once_and_new_alerts_roll_up(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.set_fields(store.devices()[0]["id"], {"important": True})

    store.record_run("lan", [], now=at(15))
    store.record_run("lan", [], now=at(30))

    assert store.queue_offline(now=at(30)) == ["192.168.10.1"]
    assert store.queue_offline(now=at(45)) == []
    offline = store.due_notifications(now=at(30))["offline"]
    store.mark_sent([item["id"] for item in offline], now=at(30))

    store.record_run("lan", [Sighting("lan", "aa:03", mac="aa:03", ip="192.168.10.3")], now=at(45))
    new = store.due_notifications(now=at(45))["new"]
    store.mark_sent([item["id"] for item in new], now=at(45))
    store.record_run("lan", [Sighting("lan", "aa:04", mac="aa:04", ip="192.168.10.4")], now=at(60))

    assert "new" not in store.due_notifications(now=at(60))
    assert "new" in store.due_notifications(now=at(60 + 24 * 60))
