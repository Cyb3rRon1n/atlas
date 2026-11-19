from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from lanxang.config.models import AtlasConfig, NotifyConfig
from lanxang.monitoring import summary

NOW = datetime(2026, 11, 19, 13, 30)                       # 08:30 in New York


def _sources(now, routes_then=None, routes_now=None, devices=None, alerts=None):
    then = [{"name": "media", "hosts": ["media.example.org"]}] if routes_then is None else routes_then
    current = [{"name": "media", "hosts": ["media.example.org"]},
               {"name": "photos", "hosts": ["photos.example.org"]}] if routes_now is None else routes_now
    listing = alerts if alerts is not None else {
        "open": [{"opened_at": now - timedelta(hours=3), "level": "problem", "title": "Printer is offline"}],
        "watch": [],
        "resolved": [{"opened_at": now - timedelta(days=2), "resolved_at": now - timedelta(hours=5),
                      "level": "problem", "title": "Backup is late"}]}
    return {
        "alerts": lambda at, days: listing,
        "devices": lambda: devices if devices is not None else [
            {"id": 1, "name": "Den TV", "ip": "192.0.2.20", "state": "new", "status": "online",
             "sightings": [{"first_seen": (now - timedelta(hours=2)).isoformat()}]},
            {"id": 2, "name": "nas", "ip": "192.0.2.5", "state": "known", "status": "quiet",
             "sightings": [{"first_seen": "2026-01-01T00:00:00"}]}],
        "changes": lambda since: [],
        "routes": lambda moment: then if moment < now - timedelta(hours=1) else current}


def test_daily_due_once_per_local_day():
    tz, at = "America/New_York", "08:00"
    eight = datetime(2026, 11, 19, 13, 0)                  # 08:00 EST
    assert not summary.daily_due(eight - timedelta(minutes=1), tz, at, None)
    assert summary.daily_due(eight + timedelta(hours=2), tz, at, None)
    assert not summary.daily_due(eight + timedelta(hours=2), tz, at, "2026-11-19")
    assert summary.daily_due(eight + timedelta(days=1), tz, at, "2026-11-19")
    assert not summary.daily_due(eight + timedelta(hours=2), tz, "", None)          # off


def test_build_daily_lists_changes():
    text, quiet = summary.build_daily(AtlasConfig(), NOW, _sources(NOW), [])
    assert text.startswith("**📋 Lanxang: yesterday**")
    for part in ("New device: Den TV (192.0.2.20)", "Printer is offline", "Cleared: Backup is late",
                 "Route added: photos.example.org", "Gone quiet: nas"):
        assert part in text, part
    assert quiet == [2]


def test_build_daily_lists_an_internet_view_alert():
    row = {"source": "internet_view", "key": "internet_view:internet_port:22", "opened_at": NOW - timedelta(hours=6),
           "resolved_at": NOW - timedelta(hours=2), "level": "problem", "title": "Port 22 is open to the internet",
           "href": "/posture"}
    same = [{"name": "media", "hosts": ["media.example.org"]}]
    sources = _sources(NOW, routes_then=same, routes_now=same, devices=[],
                       alerts={"open": [], "watch": [], "resolved": [row]})
    text, _ = summary.build_daily(AtlasConfig(), NOW, sources, [])
    assert "Port 22 is open to the internet" in text and "Cleared: Port 22 is open to the internet" in text


def test_build_daily_quiet_day_returns_none():
    same = [{"name": "media", "hosts": ["media.example.org"]}]
    sources = _sources(NOW, routes_then=same, routes_now=same, alerts={"open": [], "watch": [], "resolved": []},
                       devices=[{"id": 2, "name": "nas", "state": "known", "status": "quiet", "sightings": []}])
    assert summary.build_daily(AtlasConfig(), NOW, sources, [2]) == (None, [2])
    assert summary.build_daily(AtlasConfig(), NOW, sources, None) == (None, [2])    # first run: baseline


def test_build_daily_skips_routes_without_an_old_snapshot():
    sources = _sources(NOW, routes_then=[], alerts={"open": [], "watch": [], "resolved": []}, devices=[])
    assert summary.build_daily(AtlasConfig(), NOW, sources, [])[0] is None


def test_run_daily_respects_quiet_hours_and_off(temp_db, isolated_cwd):
    from lanxang.posture.store import PostureStore

    store, sent = PostureStore(temp_db), []
    off = AtlasConfig(notify={"timezone": "America/New_York"})
    assert summary.run_daily(off, store, NOW, send=sent.append, sources=_sources(NOW)) is None

    on = AtlasConfig(notify={"timezone": "America/New_York", "daily_summary": "08:00"})
    (isolated_cwd / "lanxang.yaml").write_text(
        "notify:\n  timezone: America/New_York\n  quiet_hours:\n    - {start: '07:00', end: '09:00'}\n")
    assert summary.run_daily(on, store, NOW, send=sent.append, sources=_sources(NOW)) is None
    assert "summary_daily" not in store.statuses() and not sent

    (isolated_cwd / "lanxang.yaml").unlink()
    for minutes in (0, 15):
        summary.run_daily(on, store, NOW + timedelta(minutes=minutes), send=sent.append, sources=_sources(NOW))
    assert len(sent) == 1 and sent[0].key == "summary:daily"
    detail = store.statuses()["summary_daily"]["detail"]
    assert detail["date"] == "2026-11-19" and detail["quiet"] == [2]


def test_run_daily_records_a_quiet_day_without_sending(temp_db, isolated_cwd):
    from lanxang.posture.store import PostureStore

    store, sent = PostureStore(temp_db), []
    on = AtlasConfig(notify={"daily_summary": "08:00"})
    same = [{"name": "media", "hosts": ["media.example.org"]}]
    sources = _sources(NOW, routes_then=same, routes_now=same, alerts={"open": [], "watch": [], "resolved": []},
                       devices=[])
    assert summary.run_daily(on, store, NOW, send=sent.append, sources=sources) is None
    detail = store.statuses()["summary_daily"]["detail"]
    assert not sent and detail["date"] == "2026-11-19" and detail["sent_at"] is None      # nothing went out


def test_run_daily_drops_a_quiet_baseline_from_weeks_ago(temp_db, isolated_cwd):
    from lanxang.posture.store import PostureStore

    store, sent = PostureStore(temp_db), []
    on = AtlasConfig(notify={"daily_summary": "08:00"})
    same = [{"name": "media", "hosts": ["media.example.org"]}]
    nas = [{"id": 2, "name": "nas", "state": "known", "status": "quiet", "sightings": []}]
    store.set_status("summary_daily", True, {"sent_at": None, "date": "2026-10-01", "quiet": []}, NOW)
    quiet_day = dict(routes_then=same, routes_now=same, alerts={"open": [], "watch": [], "resolved": []}, devices=nas)
    assert summary.run_daily(on, store, NOW, send=sent.append, sources=_sources(NOW, **quiet_day)) is None
    assert not sent                               # nas went quiet sometime in those weeks, not yesterday
    store.set_status("summary_daily", True, {"sent_at": None, "date": "2026-11-18", "quiet": []}, NOW)
    assert "Gone quiet: nas" in summary.run_daily(on, store, NOW, send=sent.append, sources=_sources(NOW, **quiet_day))


def test_routes_at_reads_the_snapshot_of_that_moment(temp_db):
    from lanxang.posture.store import PostureStore

    store = PostureStore(temp_db)
    assert store.routes_at(NOW) == []
    store.save_routes([{"name": "a", "hosts": ["a.example.org"]}], NOW - timedelta(days=2))
    store.save_routes([{"name": "b", "hosts": ["b.example.org"]}], NOW - timedelta(hours=1))
    assert store.routes_at(NOW - timedelta(days=1))[0]["name"] == "a"
    assert store.routes_at(NOW)[0]["name"] == "b"
    assert store.routes_at(NOW - timedelta(days=3)) == []


@pytest.mark.parametrize("bad", ["25:00", "8am", "12:60", "7:00"])
def test_daily_summary_rejects_bad_time(bad):
    with pytest.raises(ValidationError):
        NotifyConfig(daily_summary=bad)
    assert NotifyConfig(daily_summary="").daily_summary == ""
    assert NotifyConfig(daily_summary="23:59").daily_summary == "23:59"


def test_setup_card_saves_and_refuses_a_bad_time(isolated_cwd, temp_db):
    from lanxang.config import load_config
    from lanxang.web.settings_page import handle_post, render_settings_page

    assert handle_post("/api/settings/summary/save", {"daily_summary": "25:00"})[0] == 400
    assert handle_post("/api/settings/summary/save", {"daily_summary": "08:00"})[0] == 200
    assert load_config().notify.daily_summary == "08:00"
    assert "uses the alert time zone" in render_settings_page()
