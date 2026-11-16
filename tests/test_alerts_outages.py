from datetime import datetime

import atlas.devices.notify as notify
import atlas.notify as channels
from atlas.alerts import AlertStore
from atlas.alerts.outages import outages
from atlas.config.models import NotifyConfig, SignalNotifyConfig


def dev(id_, name, quiet=True, important=False):
    return {"id": id_, "name": name, "ip": f"192.0.2.{id_}", "status": "quiet" if quiet else "active",
            "state": "known", "important": important, "last_seen": "2026-01-01T10:00:00"}


# gateway -> core switch -> (nas, edge switch -> cam, unmanaged bridge with printer behind it)
SNAP = {"nodes": [{"id": "gw", "kind": "gateway", "device_id": 1, "behind": []},
                  {"id": "core", "kind": "switch", "device_id": None, "mac": "00:00:5E:00:53:02", "behind": []},
                  {"id": "nas", "kind": "host", "device_id": 3, "behind": []},
                  {"id": "edge", "kind": "switch", "device_id": None, "ip": "192.0.2.4", "behind": []},
                  {"id": "cam", "kind": "host", "device_id": 5, "behind": []},
                  {"id": "br", "kind": "bridge", "device_id": None, "behind": ["printer"]}],
        "links": [{"a": "gw", "b": "core"}, {"a": "core", "b": "nas"}, {"a": "core", "b": "edge"},
                  {"a": "edge", "b": "cam"}, {"a": "core", "b": "br"}]}


def devices(core_down=True):
    found = [dev(1, "gateway", quiet=False), dev(2, "core-switch", quiet=core_down), dev(3, "nas", important=True),
            dev(4, "edge-switch"), dev(5, "cam", important=True), dev(6, "printer"), dev(7, "laptop", important=True)]
    found[1]["sightings"] = [{"mac": "00:00:5e:00:53:02"}]           # core switch matched by MAC, edge by IP
    return found


def test_topmost_down_box_takes_everything_behind_it():

    found = outages([SNAP], devices())
    assert set(found) == {2} and sorted(found[2]) == [3, 4, 5, 6]  # edge switch folds under core, not its own
    assert outages([SNAP], devices(core_down=False)) == {4: [5]}
    assert outages([], devices()) == {}
    newest_without_core = {"nodes": [SNAP["nodes"][0]], "links": []}
    assert set(outages([newest_without_core, SNAP], devices())) == {2}   # older scan still says what was behind


def test_alerts_page_gets_one_alert_per_outage(temp_db):

    store, now = AlertStore(), datetime(2026, 1, 1, 12)
    notify.report_alerts(store, devices(), now, snaps=[SNAP])
    titles = [row["title"] for row in store.listing(now)["open"]]

    assert "core-switch is offline - 4 devices behind it unreachable" in titles
    assert "laptop is offline" in titles                           # not behind anything down
    assert not any(title.startswith(("nas", "cam")) for title in titles)


class Store:

    def __init__(self, items):
        self.items, self.sent = items, []

    def due_notifications(self, now=None):
        return {"offline": self.items}

    def devices(self, now=None):
        return devices()

    def mark_sent(self, ids, now=None):
        self.sent += ids


def test_one_message_line_per_outage(monkeypatch, temp_db):

    sent = []
    monkeypatch.setattr(channels, "send_signal", lambda config, text: (sent.append(text), (True, ""))[1])
    items = [{"id": n, "device_id": d, "device": name, "ip": None, "last_seen": None}
             for n, d, name in ((10, 3, "nas"), (11, 5, "cam"), (12, 7, "laptop"))]
    store = Store(items)

    assert notify.deliver(store, NotifyConfig(signal=SignalNotifyConfig(url="http://x")), snaps=[SNAP]) == []
    assert sorted(store.sent) == [10, 11, 12]
    text = sent[0]
    assert "core-switch (192.0.2.2) and 4 devices behind it" in text and "• laptop" in text
    assert "• nas" not in text and "• cam" not in text
