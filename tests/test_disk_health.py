from datetime import datetime, timedelta

from atlas.config.models import AtlasConfig, HealthConfig
from atlas.monitoring import disks
from atlas.proxmox.discovery import discover_node_storage, smart_numbers
from atlas.web.home_page import build_storage


def test_smart_numbers_from_ata_attributes_and_nvme_text():
    ata = {"attributes": [{"id": "  5", "raw": "1"}, {"id": "194", "raw": "36 (Min/Max 19/57)"},
                          {"id": "197", "raw": "2"}, {"id": "9", "raw": "8433"}]}
    assert smart_numbers(ata) == {"temp": 36, "bad": 3}
    assert smart_numbers({"attributes": [{"id": "190", "raw": "41"}]}) == {"temp": 41, "bad": None}
    nvme = {"type": "text", "text": "Temperature:                        48 Celsius\n"
                                    "Media and Data Integrity Errors:    0\n"}
    assert smart_numbers(nvme) == {"temp": 48, "bad": 0}
    assert smart_numbers({}) == {"temp": None, "bad": None}


class FakeProxmox:
    """client.nodes(name).disks.list.get() / .smart.get(disk=...), as proxmoxer chains them."""

    def __init__(self, smart_fails=False):
        self.smart_fails = smart_fails

    def nodes(self, name):
        return self

    def __getattr__(self, part):
        if part in ("storage", "zfs"):
            raise RuntimeError("no Sys.Audit")
        self.part = part
        return self

    def get(self, disk=None):
        if self.part == "list":
            return [{"devpath": "/dev/sda", "type": "ssd", "model": "Example_SSD_2TB", "size": 2 * 10**12,
                     "health": "PASSED", "wearout": 92, "serial": "S1", "used": "ZFS"},
                    {"devpath": "/dev/sdb", "type": "hdd", "model": "Example HDD", "health": "PASSED",
                     "wearout": "N/A"}]
        if self.smart_fails:
            raise RuntimeError("smart off")
        return {"attributes": [{"id": "194", "raw": "40"}, {"id": "5", "raw": "0"}]}


def test_node_storage_lists_disks_and_survives_missing_smart():
    disks_ = discover_node_storage(FakeProxmox(), "pve")["disks"]
    assert disks_[0] == {"dev": "/dev/sda", "type": "ssd", "size": 2 * 10**12, "model": "Example SSD 2TB",
                         "serial": "S1", "health": "PASSED", "used": "ZFS", "life": 92, "temp": 40, "bad": 0}
    assert disks_[1]["life"] is None                                 # "N/A" on a spinning disk
    no_smart = discover_node_storage(FakeProxmox(smart_fails=True), "pve")["disks"]
    assert no_smart[0]["health"] == "PASSED" and "temp" not in no_smart[0]


def _disk(**kw):
    return {"dev": "/dev/sda", "type": "ssd", "model": "Example SSD", "serial": "S1", "health": "PASSED",
            "life": 90, "temp": 40, "bad": 1, **kw}


def test_alerts_once_per_problem_and_once_when_it_clears(temp_db):
    from atlas.posture.store import PostureStore

    store, sent = PostureStore(temp_db), []
    settings = AtlasConfig()
    t = datetime(2026, 11, 17, 9)
    scans = [_disk(), _disk(temp=75), _disk(temp=76), _disk(temp=77, bad=4), _disk(temp=50, bad=4),
             _disk(health="FAILED", life=8)]
    for i, disk in enumerate(scans):
        disks.run(settings, store, t + timedelta(minutes=15 * i), [{"name": "pve", "disks": [disk]}],
                  send=sent.append)
    assert [s.key for s in sent] == ["disks:hot:pve:S1", "disks:bad:pve:S1", "disks:hot:pve:S1",
                                     "disks:failed:pve:S1", "disks:worn:pve:S1"]
    assert "running hot" in sent[0] and "77" not in sent[0]           # one hot scan alone said nothing
    assert "from 1 to 4" in sent[1] and "no longer running hot" in sent[2]
    status = store.statuses()["disks"]
    assert not status["ok"] and status["detail"]["disks"]["pve:S1"]["problems"] == ["failed", "worn"]


def test_spinning_disks_have_a_lower_heat_limit_and_no_wear():
    health = HealthConfig()
    assert "hot" in disks.problems({"type": "hdd", "temp": 56, "life": 5}, health, was_hot=True)
    assert disks.problems({"type": "hdd", "temp": 56, "life": 5}, health, was_hot=True).keys() == {"hot"}
    assert not disks.problems({"type": "ssd", "temp": 56, "life": 50}, health, was_hot=True)


def test_home_storage_card_sums_disks_and_lists_problem_ones():
    scan = {"nodes": [{"name": "pve", "zfs": [], "disks": [_disk(), _disk(dev="/dev/sdb", serial="S2", temp=48),
                                                         _disk(dev="/dev/sdc", serial="S3", life=5)]}]}
    rows = build_storage([], {}, {}, scan)["rows"]
    assert rows[0] == {"name": "pve disks", "detail": "3 disks · 1 needs a look · warmest 48°C · lowest life left 5%",
                       "warn": True}
    assert rows[1]["name"] == "pve /dev/sdc" and "worn out" in rows[1]["detail"]
    healthy = build_storage([], {}, {}, {"nodes": [{"name": "pve", "disks": [_disk()]}]})
    assert healthy["state"] == "ok" and "all healthy" in healthy["rows"][0]["detail"]
