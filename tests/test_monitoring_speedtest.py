from datetime import datetime
from types import SimpleNamespace

from lanxang.monitoring import speedtest


class Store:
    def __init__(self):
        self.saved = {}

    def statuses(self):
        return {k: {"detail": v} for k, v in self.saved.items()}

    def set_status(self, source, ok, detail, now):
        self.saved[source] = detail


SETTINGS = SimpleNamespace(notify=SimpleNamespace(timezone="America/New_York"))
RESULT = {"down": 1880.5, "up": 940.2, "ping": 9}


def test_runs_once_a_day_after_four_local():

    store, calls = Store(), []

    def test():
        calls.append(1)
        return RESULT

    night = datetime(2026, 11, 20, 8, 30)           # 03:30 in New York: too early
    assert speedtest.run(SETTINGS, store, night, test=test) == {} and not calls
    morning = datetime(2026, 11, 20, 9, 5)          # 04:05 in New York
    detail = speedtest.run(SETTINGS, store, morning, test=test)
    assert detail["down"] == 1880.5 and detail["error"] is None and len(detail["history"]) == 1
    speedtest.run(SETTINGS, store, datetime(2026, 11, 20, 20, 0), test=test)   # same local day
    assert len(calls) == 1
    detail = speedtest.run(SETTINGS, store, datetime(2026, 11, 21, 9, 5), test=test)
    assert len(calls) == 2 and len(detail["history"]) == 2
    detail = speedtest.run(SETTINGS, store, datetime(2026, 12, 25, 9, 5), test=test)   # a month later: old ones go
    assert len(detail["history"]) == 1


def test_a_failure_is_saved_not_raised():

    def test():
        raise OSError("timed out")

    store = Store()
    detail = speedtest.run(SETTINGS, store, datetime(2026, 11, 20, 9, 5), test=test)
    assert detail["error"] == "timed out" and detail["down"] is None and detail["history"] == []


def test_measure_counts_every_stream():

    sent = []

    def request(url, data=None, timeout=60):
        sent.append((url, len(data) if data else 0))

    result = speedtest.measure(request, ping=lambda: 9)
    assert result["ping"] == 9 and result["down"] > 0 and result["up"] > 0
    downs = [u for u, _ in sent if f"bytes={speedtest.DOWN_BYTES}" in u]
    ups = [n for u, n in sent if u.endswith("/__up")]
    assert len(downs) == speedtest.STREAMS and ups == [speedtest.UP_BYTES] * speedtest.STREAMS
