from datetime import datetime, timedelta

from atlas.config.models import AtlasConfig
from atlas.monitoring import summary

SUNDAY_EVENING = datetime(2026, 11, 15, 23, 30)            # 18:30 in Detroit


def _sources(now):
    return {
        "internet_rows": lambda since: [(now - timedelta(days=2) + timedelta(minutes=m), m >= 3, True) for m in range(10)],
        "uptime_summary": lambda names: {"Media": {"uptime": {"7 days": 99.5}}, "Photos": {"uptime": {"7 days": 100.0}}},
        "devices": lambda: [{"name": "Den TV", "state": "new",
                             "sightings": [{"first_seen": (now - timedelta(days=1)).isoformat()}]},
                            {"name": "nas", "state": "known", "sightings": [{"first_seen": "2026-01-01T00:00:00"}]}],
        "alerts": lambda: [{"level": "problem", "title": "Printer is offline"}, {"level": "watch", "title": "x"}],
        "statuses": lambda: {"heartbeats": {"detail": {"Backup": {"state": "ok"}, "Pull": {"state": "late"},
                                                       "New": {"state": "waiting"}}}},
        "disks": lambda statuses: [("pve", [{"type": "ssd", "health": "PASSED", "temp": 41, "life": 90}])]}


def test_the_week_in_short_lines():
    settings = AtlasConfig(uptime={"checks": [{"name": "Media", "target": "https://m.example.org"},
                                              {"name": "Photos", "target": "https://p.example.org"}]})
    text = summary.build(settings, SUNDAY_EVENING, _sources(SUNDAY_EVENING))
    assert text.startswith("**📋 Atlas: your week**")
    for part in ("Internet: 1 outage, 3 min in all", "Services: 1 of 2 up all week; Media 99.5%",
                 "Devices: 2, 1 new this week (Den TV); 1 waiting", "Alerts: 1 problem open (Printer is offline), 1 to watch",
                 "Heartbeats: 1 of 2 on time; not: Pull", "Disks: 1, all healthy, warmest 41°C"):
        assert part in text, part


def test_due_on_sunday_evening_local_once_a_week():
    assert summary.due(SUNDAY_EVENING, "America/Detroit", None)
    assert not summary.due(SUNDAY_EVENING - timedelta(hours=1), "America/Detroit", None)       # 17:30 local
    assert not summary.due(SUNDAY_EVENING, "America/Detroit", (SUNDAY_EVENING - timedelta(hours=2)).isoformat())
    assert summary.due(SUNDAY_EVENING, "America/Detroit", (SUNDAY_EVENING - timedelta(days=7)).isoformat())
    assert not summary.due(SUNDAY_EVENING + timedelta(days=1), "America/Detroit", None)        # Monday


def test_run_sends_once_and_can_be_turned_off(temp_db, isolated_cwd):
    from atlas.posture.store import PostureStore

    store, sent = PostureStore(temp_db), []
    settings = AtlasConfig(notify={"timezone": "America/Detroit"})
    for minutes in (0, 15, 30):
        summary.run(settings, store, SUNDAY_EVENING + timedelta(minutes=minutes), send=sent.append,
                    sources=_sources(SUNDAY_EVENING))
    assert len(sent) == 1 and sent[0].key == "summary:weekly"
    off = AtlasConfig(notify={"timezone": "America/Detroit", "weekly_summary": False})
    assert summary.run(off, PostureStore(temp_db), SUNDAY_EVENING + timedelta(days=7), send=sent.append) is None
