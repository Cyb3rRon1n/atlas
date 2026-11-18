from datetime import datetime

from lanxang.alerts import Text, allowed
from lanxang.alerts.quiet import active, describe, minutes
from lanxang.config.models import QuietHours
from lanxang.web.alerts_page import handle_post, render_alerts_page


def test_windows_by_day_over_midnight_and_time_zone():
    night = QuietHours(start="23:00", end="07:00")
    sunday = QuietHours(start="03:00", end="06:00", days=["sun"])
    # 2026-11-15 is a Sunday; Detroit is UTC-5 in November
    assert active([sunday], "America/Detroit", datetime(2026, 11, 15, 9, 30))          # 04:30 local Sunday
    assert not active([sunday], "America/Detroit", datetime(2026, 11, 15, 4, 30))      # 23:30 local Saturday
    assert not active([sunday], "", datetime(2026, 11, 16, 4, 0))                      # Monday 04:00 UTC
    assert active([night], "", datetime(2026, 11, 17, 23, 30)) and active([night], "", datetime(2026, 11, 18, 6, 59))
    assert not active([night], "", datetime(2026, 11, 18, 7, 0))
    friday_night = QuietHours(start="22:00", end="02:00", days=["fri"])
    assert active([friday_night], "", datetime(2026, 11, 21, 1, 0))                    # Saturday 01:00 = Friday's
    assert not active([friday_night], "", datetime(2026, 11, 22, 1, 0))                # Sunday 01:00
    assert active([sunday], "Not/AZone", datetime(2026, 11, 15, 4, 0))                 # unknown zone = UTC
    assert describe(night) == "every day 23:00-07:00" and describe(sunday) == "Sun 03:00-06:00"
    assert minutes("06:30") == 390


def test_messages_are_held_in_quiet_hours(isolated_cwd):
    (isolated_cwd / "atlas.yaml").write_text("notify:\n  quiet_hours:\n    - {start: '23:00', end: '07:00'}\n")
    text = Text("**x**", "uptime:down:x")
    assert not allowed(None, text, datetime(2026, 11, 17, 2, 0))
    assert allowed(None, text, datetime(2026, 11, 17, 12, 0))
    (isolated_cwd / "atlas.yaml").write_text("notify:\n  quiet_hours:\n    - {start: 'bad', end: '07:00'}\n")
    assert allowed(None, text, datetime(2026, 11, 17, 2, 0))                         # a bad schedule fails open


def test_alerts_page_adds_shows_and_removes_quiet_hours(isolated_cwd, temp_db):
    from lanxang.config import load_config

    body = {"start": "03:00", "end": "06:00", "days": ["sun"], "timezone": "America/Detroit"}
    assert handle_post("/api/alerts/quiet-hours/add", body) == (200, {"ok": True})
    assert handle_post("/api/alerts/quiet-hours/add", {**body, "days": []})[0] == 400
    assert handle_post("/api/alerts/quiet-hours/add", {**body, "end": "03:00"})[0] == 400
    assert handle_post("/api/alerts/quiet-hours/add", {**body, "start": "25:00"})[0] == 400
    notify = load_config().notify
    assert notify.timezone == "America/Detroit" and notify.quiet_hours[0].days == ["sun"]
    html = render_alerts_page({"open": [], "watch": [], "resolved": [], "muted": [], "paused_until": None},
                              datetime(2026, 11, 15, 9, 0), notify)
    assert "Sun 03:00-06:00" in html and "on now" in html and "America/Detroit" in html
    assert handle_post("/api/alerts/quiet-hours/0/remove", {}) == (200, {"ok": True})
    assert handle_post("/api/alerts/quiet-hours/0/remove", {})[0] == 404 and load_config().notify.quiet_hours == []
