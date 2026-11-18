from datetime import datetime, timedelta

from lanxang.wiring.store import WiringStore, diff_snapshots


def _snap(port="gi5", speed=1000, up=True):
    return {"nodes": [{"id": "s:core", "name": "core-switch", "kind": "switch"},
                      {"id": "h:1", "name": "nas", "kind": "host"}],
            "links": [{"id": f"s:core|{port}|h:1|", "a": "s:core", "a_port": port, "b": "h:1", "b_port": "",
                       "speed": speed, "up": up}], "panels": [], "warnings": []}


def test_save_latest_prune(temp_db):
    store = WiringStore()
    t0 = datetime(2026, 1, 1)
    for i in range(4):
        store.save(_snap(), {"switches": {}}, {"core-switch": {"ok": True}}, t0 + timedelta(minutes=i), keep=3)
    rows = store.latest(10)
    assert len(rows) == 3 and rows[0]["taken_at"] == t0 + timedelta(minutes=3)
    assert rows[0]["sources"] == {"core-switch": {"ok": True}} and rows[0]["raw"] == {"switches": {}}


def test_diff():
    assert diff_snapshots(None, _snap()) == []
    moved = diff_snapshots(_snap("gi5"), _snap("gi7"))
    assert {"type": "moved", "text": "nas moved: core-switch gi5 → core-switch gi7"} in moved
    assert diff_snapshots(_snap(speed=1000), _snap(speed=100))[0]["type"] == "speed"
    assert diff_snapshots(_snap(up=True), _snap(up=False))[0]["type"] == "down"
    gone = dict(_snap(), links=[])
    assert diff_snapshots(_snap(), gone)[0]["type"] == "removed"
    assert diff_snapshots(gone, _snap())[0]["type"] == "added"