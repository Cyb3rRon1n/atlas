import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from atlas.config.models import MapHost
from atlas.database.models import DeviceRecord
from atlas.devices import Sighting
from atlas.devices.store import CONNECTIONS, KINDS, InventoryStore


T0 = datetime(2026, 9, 30, 12, 0)


def at(minutes):

    return T0 + timedelta(minutes=minutes)


def seeded(temp_db):
    """mediabox (known: manual + lan) and a proxmox guest suggested into it, plus a new phone."""

    store = InventoryStore(temp_db)
    store.import_manual_hosts([MapHost(name="mediabox", address="192.168.10.57")], now=T0)
    store.record_run("lan", [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57"),
                             Sighting("lan", "aa:88", ip="192.168.10.88", mac="aa:88", hostname="pixel.lan")], now=at(0))
    store.record_run("proxmox", [Sighting("proxmox", "pve:200", hostname="mediabox", detail={"type": "lxc"})], now=at(0))

    devices = store.devices()  # a list: the guest and the known device are both named "mediabox"
    known = next(d for d in devices if d["state"] == "known")
    guest = next(d for d in devices if d["suggested_merge_id"] == known["id"])
    phone = next(d for d in devices if d["name"] == "pixel")

    return store, known, guest, phone


def test_set_fields_validates_everything_before_applying(temp_db):

    store, known, guest, phone = seeded(temp_db)

    assert store.set_fields(phone["id"], {"name": "Pixel 7", "kind": "toaster"}) == \
        {"found": True, "error": f"kind must be one of: {', '.join(KINDS)}"}
    assert store.device(phone["id"])["name"] == "pixel"

    for bad in ({"name": "  "}, {"state": "gone"}, {"important": "yes"}, {"tags": "a,b"},
                {"tags": ["x" * 33]}, {"notes": "n" * 2001}, {"id": 5}):
        assert "error" in store.set_fields(phone["id"], bad), bad

    assert store.set_fields(999, {"name": "x"}) == {"found": False}


def test_set_fields_applies_locks_and_clears_suggestion_when_triaged(temp_db):

    store, known, guest, phone = seeded(temp_db)

    assert store.set_fields(phone["id"], {"name": " Pixel 7 ", "kind": "phone", "tags": ["family"],
                                          "important": True, "state": "known"}) == {"found": True}
    phone = store.device(phone["id"])
    assert (phone["name"], phone["kind"], phone["tags"], phone["important"], phone["state"]) == \
        ("Pixel 7", "phone", ["family"], True, "known")

    store.set_fields(guest["id"], {"state": "ignored"})
    assert store.device(guest["id"])["suggested_merge_id"] is None


def test_set_fields_validates_connection(temp_db):

    store, known, guest, phone = seeded(temp_db)

    assert store.set_fields(phone["id"], {"connection": "bluetooth"}) == \
        {"found": True, "error": f"connection must be one of: {', '.join(CONNECTIONS)}"}

    assert store.set_fields(phone["id"], {"connection": "wired"}) == {"found": True}
    assert store.device(phone["id"])["connection"] == "wired"


def test_set_fields_validates_uplink_id_before_applying_anything(temp_db):

    store, known, guest, phone = seeded(temp_db)

    assert store.set_fields(phone["id"], {"uplink_id": "x"}) == \
        {"found": True, "error": "uplink_id must be a device id or null"}
    assert store.set_fields(phone["id"], {"uplink_id": True}) == \
        {"found": True, "error": "uplink_id must be a device id or null"}
    assert store.set_fields(phone["id"], {"uplink_id": 2 ** 63}) == \
        {"found": True, "error": "uplink_id must be a device id or null"}
    assert store.set_fields(phone["id"], {"uplink_id": -1}) == \
        {"found": True, "error": "uplink_id must be a device id or null"}
    assert store.set_fields(phone["id"], {"uplink_id": 0}) == \
        {"found": True, "error": "uplink_id must be a device id or null"}
    assert store.set_fields(phone["id"], {"uplink_id": phone["id"]}) == \
        {"found": True, "error": "a device can't be connected to itself"}
    assert store.set_fields(phone["id"], {"uplink_id": 999999}) == \
        {"found": True, "error": "uplink_id must be an existing device"}
    assert store.device(phone["id"])["uplink_id"] is None

    assert store.set_fields(phone["id"], {"uplink_id": known["id"]}) == {"found": True}
    assert store.device(phone["id"])["uplink_id"] == known["id"]

    assert store.set_fields(phone["id"], {"uplink_id": None}) == {"found": True}
    assert store.device(phone["id"])["uplink_id"] is None


def test_connection_and_uplink_id_get_locked(temp_db):

    store, known, guest, phone = seeded(temp_db)

    store.set_fields(phone["id"], {"connection": "wired", "uplink_id": known["id"]})

    with Session(store.engine) as session:
        locked = set(json.loads(session.get(DeviceRecord, phone["id"]).locked_fields))

    assert {"connection", "uplink_id"} <= locked


def test_merge_repoints_uplinks_and_clears_a_resulting_self_reference(temp_db):

    store, known, guest, phone = seeded(temp_db)

    store.set_fields(phone["id"], {"uplink_id": guest["id"]})
    store.set_fields(known["id"], {"uplink_id": guest["id"]})

    store.merge(guest["id"], known["id"])

    assert store.device(phone["id"])["uplink_id"] == known["id"]
    assert store.device(known["id"])["uplink_id"] is None


def test_devices_exposes_connection_fields(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "00:11:32:aa:bb:cc", ip="192.168.10.5", mac="00:11:32:aa:bb:cc")])

    device = store.devices()[0]
    assert device["connection"] == "unknown"
    assert device["connection_guessed"] is False
    assert device["uplink_id"] is None

    store.set_fields(device["id"], {"connection": "wired"})
    device = store.device(device["id"])
    assert device["connection"] == "wired"
    assert device["connection_guessed"] is False


def test_devices_guesses_wireless_from_a_locally_administered_mac(temp_db):
    """The effective connection is the guess, but the stored value underneath
    stays "unknown" - recoverable, not silently overwritten by the guess."""

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "da:a1:19:00:00:01", ip="192.168.10.6", mac="da:a1:19:00:00:01")])

    device = store.devices()[0]
    assert device["connection"] == "wireless"
    assert device["connection_guessed"] is True

    with Session(store.engine) as session:
        assert session.get(DeviceRecord, device["id"]).connection == "unknown"


def test_merge_moves_sightings_and_notifications_and_deletes_source(temp_db):

    store, known, guest, phone = seeded(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:99", ip="192.168.10.99", mac="aa:99")], now=at(15))
    newcomer = next(d for d in store.devices() if d["ip"] == "192.168.10.99")

    assert store.merge(guest["id"], known["id"]) == {"found": True, "device_id": known["id"]}
    assert store.device(guest["id"]) is None
    assert {s["source"] for s in store.device(known["id"])["sightings"]} == {"manual", "lan", "proxmox"}

    # newcomer's queued "new" alert moves with it, so it now names the phone
    assert store.merge(newcomer["id"], phone["id"])["device_id"] == phone["id"]
    assert [item["device"] for item in store.due_notifications(now=at(15))["new"]] == ["pixel"]

    assert store.merge(known["id"], known["id"]) == {"found": True, "error": "can't merge a device into itself"}
    assert store.merge(12345, known["id"]) == {"found": False}
    assert store.merge(99999, 99999) == {"found": False}


def test_merge_dedupes_queued_new_alerts(temp_db):
    """Both new devices already have a queued "new" alert - merging must leave exactly
    one due item for the target, not two (which would double-alert on one device)."""

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.record_run("lan", [Sighting("lan", "aa:02", ip="192.168.10.2", mac="aa:02")], now=at(15))
    store.record_run("lan", [Sighting("lan", "aa:03", ip="192.168.10.3", mac="aa:03")], now=at(30))

    devices = store.devices(now=at(30))
    target = next(d for d in devices if d["ip"] == "192.168.10.2")
    source = next(d for d in devices if d["ip"] == "192.168.10.3")

    assert store.merge(source["id"], target["id"]) == {"found": True, "device_id": target["id"]}

    due = store.due_notifications(now=at(30))["new"]
    assert len(due) == 1
    assert due[0]["device"] == target["name"]


def test_split_makes_a_new_device_but_never_empties_one(temp_db):

    store, known, guest, phone = seeded(temp_db)
    lan = next(s for s in store.device(known["id"])["sightings"] if s["source"] == "lan")

    result = store.split(lan["id"])
    assert result["found"] is True and result["device_id"] != known["id"]
    assert store.device(result["device_id"])["state"] == "new"
    assert [s["source"] for s in store.device(known["id"])["sightings"]] == ["manual"]

    only = store.device(phone["id"])["sightings"][0]
    assert store.split(only["id"]) == {"found": True, "error": "that's the device's only sighting"}
    assert store.split(99999) == {"found": False}


def test_split_sets_kind_from_the_sighting_type(temp_db):
    """A proxmox lxc sighting split off its device becomes its own device with kind "lxc"."""

    store = InventoryStore(temp_db)
    store.import_manual_hosts([MapHost(name="mediabox", address="192.168.10.57")], now=T0)
    store.record_run("proxmox", [Sighting("proxmox", "pve:200", ip="192.168.10.57", detail={"type": "lxc"})], now=at(0))

    known = store.devices(now=at(0))[0]
    assert {s["source"] for s in known["sightings"]} == {"manual", "proxmox"}

    proxmox_sighting = next(s for s in known["sightings"] if s["source"] == "proxmox")
    result = store.split(proxmox_sighting["id"])

    assert result["found"] is True
    assert store.device(result["device_id"])["kind"] == "lxc"


def test_triage_lists_new_with_suggestion_names_and_quiet_known(temp_db):

    store, known, guest, phone = seeded(temp_db)
    store.set_fields(phone["id"], {"state": "known"})
    store.record_run("lan", [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57")], now=at(15))
    store.record_run("lan", [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57")], now=at(30))

    triage = store.triage()

    assert [(d["name"], d["suggested_merge_name"]) for d in triage["new"]] == [("mediabox", "mediabox")]
    assert [d["name"] for d in triage["quiet"]] == ["pixel"]


def test_coverage_reports_each_source_and_quiet_invisible(temp_db):

    store, known, guest, phone = seeded(temp_db)
    store.import_manual_hosts([MapHost(name="garage-tv", address="192.168.10.224")], now=at(1))
    store.record_run("proxmox", [], ok=False, error="could not connect to Proxmox", now=at(15))

    coverage = store.coverage()
    sources = {s["source"]: s for s in coverage["sources"]}

    assert sources["proxmox"]["ok"] is False
    assert sources["proxmox"]["error"] == "could not connect to Proxmox"
    assert sources["proxmox"]["last_ok"] == at(0).isoformat()
    assert sources["lan"]["ok"] is True and sources["lan"]["seen_count"] == 2
    assert [d["name"] for d in coverage["invisible"]] == ["garage-tv"]
    assert coverage["quiet"] == []
